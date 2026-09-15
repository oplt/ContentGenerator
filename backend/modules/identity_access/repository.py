from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.tenant_cache import (
    OWNER_IDENTITY,
    CachePolicy,
    build_cache_key,
    hydrate_orm,
    orm_column_dict,
    tenant_cache,
)
from backend.core.time_utils import utc_now_naive
from backend.modules.identity_access.models import (
    MembershipStatus,
    Permission,
    RefreshSession,
    Role,
    Tenant,
    TenantStatus,
    TenantUser,
    User,
)

_TENANT_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)
_PERM_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=0)
_ROLE_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)


class IdentityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        # Never cache User rows — contain password_hash / MFA secrets (T3.3).
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID | str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None,
        is_admin: bool = False,
        is_verified: bool = False,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            is_admin=is_admin,
            is_verified=is_verified,
        )
        self.db.add(user)
        await self.db.flush()
        # Drop any legacy credential-bearing keys from pre-T3.3 caches.
        await tenant_cache.delete(
            f"user_by_email:{email.lower()}",
            f"user_by_id:{user.id}",
        )
        return user

    async def create_tenant(self, *, name: str, slug: str) -> Tenant:
        tenant = Tenant(name=name, slug=slug, status=TenantStatus.TRIAL.value)
        self.db.add(tenant)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(
                owner=OWNER_IDENTITY,
                tenant_id=tenant.id,
                identity="tenant:self",
            ),
            build_cache_key(
                owner=OWNER_IDENTITY,
                global_scope=True,
                identity=f"tenant_by_slug:{slug}",
            ),
            build_cache_key(
                owner=OWNER_IDENTITY,
                global_scope=True,
                identity="active_tenants",
            ),
            f"tenant_by_slug:{slug}",
            f"tenant_by_id:{tenant.id}",
            "active_tenants",
        )
        return tenant

    async def get_tenant_by_id(self, tenant_id: uuid.UUID | str) -> Tenant | None:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            tenant_id=tenant_id,
            identity="tenant:self",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalar_one_or_none()
            return orm_column_dict(tenant) if tenant else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_TENANT_POLICY,
            factory=_load,
            legacy_keys=[f"tenant_by_id:{tenant_id}"],
        )
        return hydrate_orm(Tenant, payload) if payload else None

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity=f"tenant_by_slug:{slug}",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
            tenant = result.scalar_one_or_none()
            return orm_column_dict(tenant) if tenant else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_TENANT_POLICY,
            factory=_load,
            legacy_keys=[f"tenant_by_slug:{slug}"],
        )
        return hydrate_orm(Tenant, payload) if payload else None

    async def list_user_memberships(self, user_id: uuid.UUID | str) -> list[TenantUser]:
        # Needs eager role; skip cache to avoid stale detached graphs.
        result = await self.db.execute(
            select(TenantUser)
            .options(selectinload(TenantUser.role))
            .where(
                TenantUser.user_id == user_id,
                TenantUser.membership_status == MembershipStatus.ACTIVE.value,
                TenantUser.deleted_at.is_(None),
            )
            .order_by(TenantUser.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_membership(
        self, *, user_id: uuid.UUID | str, tenant_id: uuid.UUID | str
    ) -> TenantUser | None:
        result = await self.db.execute(
            select(TenantUser)
            .options(selectinload(TenantUser.role))
            .where(
                TenantUser.user_id == user_id,
                TenantUser.tenant_id == tenant_id,
                TenantUser.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_membership(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role | None,
        title: str | None = None,
    ) -> TenantUser:
        membership = TenantUser(
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=role.id if role else None,
            title=title,
            membership_status=MembershipStatus.ACTIVE.value,
        )
        self.db.add(membership)
        await self.db.flush()
        await tenant_cache.delete(
            f"user_memberships:{user_id}",
            f"membership:{user_id}:{tenant_id}",
        )
        return membership

    async def list_permissions(self) -> list[Permission]:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity="permissions:all",
        )

        async def _load() -> list[dict] | None:
            result = await self.db.execute(select(Permission).order_by(Permission.code.asc()))
            permissions = list(result.scalars().all())
            return [orm_column_dict(p) for p in permissions]

        payload = await tenant_cache.get_or_set(
            key,
            policy=_PERM_POLICY,
            factory=_load,
            legacy_keys=["all_permissions"],
        )
        if not payload:
            return []
        return [hydrate_orm(Permission, item) for item in payload]

    async def get_permission_by_code(self, code: str) -> Permission | None:
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity=f"permission:{code}",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(select(Permission).where(Permission.code == code))
            permission = result.scalar_one_or_none()
            return orm_column_dict(permission) if permission else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_PERM_POLICY,
            factory=_load,
            legacy_keys=[f"permission_by_code:{code}"],
        )
        return hydrate_orm(Permission, payload) if payload else None

    async def create_permission(self, *, code: str, description: str, category: str) -> Permission:
        permission = Permission(code=code, description=description, category=category)
        self.db.add(permission)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity="permissions:all"),
            build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity=f"permission:{code}"),
            "all_permissions",
            f"permission_by_code:{code}",
        )
        return permission

    async def get_role(self, *, tenant_id: uuid.UUID | None, slug: str) -> Role | None:
        if tenant_id is None:
            key = build_cache_key(
                owner=OWNER_IDENTITY,
                global_scope=True,
                identity=f"role:{slug}",
            )
            legacy = [f"role:None:{slug}", f"role:{tenant_id}:{slug}"]
        else:
            key = build_cache_key(
                owner=OWNER_IDENTITY,
                tenant_id=tenant_id,
                identity=f"role:{slug}",
            )
            legacy = [f"role:{tenant_id}:{slug}"]

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.slug == slug)
            )
            role = result.scalar_one_or_none()
            return orm_column_dict(role) if role else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_ROLE_POLICY,
            factory=_load,
            legacy_keys=legacy,
        )
        return hydrate_orm(Role, payload) if payload else None

    async def create_role(
        self,
        *,
        tenant_id: uuid.UUID | None,
        name: str,
        slug: str,
        description: str,
        is_system: bool,
        permission_codes: list[str],
    ) -> Role:
        role = Role(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            is_system=is_system,
            permission_codes=permission_codes,
        )
        self.db.add(role)
        await self.db.flush()
        keys = [
            f"role:{tenant_id}:{slug}",
        ]
        if tenant_id is None:
            keys.append(
                build_cache_key(owner=OWNER_IDENTITY, global_scope=True, identity=f"role:{slug}")
            )
        else:
            keys.append(
                build_cache_key(
                    owner=OWNER_IDENTITY, tenant_id=tenant_id, identity=f"role:{slug}"
                )
            )
        if is_system:
            keys.extend(
                [
                    build_cache_key(
                        owner=OWNER_IDENTITY, global_scope=True, identity="permissions:all"
                    ),
                    "all_permissions",
                ]
            )
        await tenant_cache.delete(*keys)
        return role

    async def create_refresh_session(
        self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime
    ) -> RefreshSession:
        session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.flush()
        await tenant_cache.delete(
            f"active_sessions:{user_id}",
            f"refresh_session_by_hash:{token_hash}",
        )
        return session

    async def get_refresh_session_by_hash(self, token_hash: str) -> RefreshSession | None:
        # Never cache refresh sessions — auth material (T3.3).
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: uuid.UUID | str) -> RefreshSession | None:
        result = await self.db.execute(select(RefreshSession).where(RefreshSession.id == session_id))
        return result.scalar_one_or_none()

    async def revoke_refresh_session(self, session: RefreshSession) -> None:
        session.is_revoked = True
        await self.db.flush()
        await tenant_cache.delete(
            f"refresh_session_by_hash:{session.token_hash}",
            f"refresh_session_by_id:{session.id}",
            f"active_sessions:{session.user_id}",
        )

    async def list_active_sessions(self, user_id: uuid.UUID) -> list[RefreshSession]:
        result = await self.db.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > utc_now_naive(),
            )
        )
        return list(result.scalars().all())


class TenantRepository:
    """Thin wrapper for tenant-level queries used by workers."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_active_tenants(self) -> list[Tenant]:
        """Return all non-suspended tenants for beat-scheduled fan-out tasks."""
        key = build_cache_key(
            owner=OWNER_IDENTITY,
            global_scope=True,
            identity="active_tenants",
        )

        async def _load() -> list[dict] | None:
            result = await self.db.execute(
                select(Tenant).where(
                    Tenant.status != TenantStatus.SUSPENDED.value,
                    Tenant.deleted_at.is_(None),
                )
            )
            tenants = list(result.scalars().all())
            return [orm_column_dict(t) for t in tenants]

        payload = await tenant_cache.get_or_set(
            key,
            policy=CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=600),
            factory=_load,
            legacy_keys=["active_tenants"],
        )
        if not payload:
            return []
        return [hydrate_orm(Tenant, item) for item in payload]
