"""User, tenant, and membership persistence with identity cache."""

from __future__ import annotations

import uuid

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
from backend.modules.identity_access.models import (
    MembershipStatus,
    Role,
    Tenant,
    TenantStatus,
    TenantUser,
    User,
)

_TENANT_POLICY = CachePolicy(owner=OWNER_IDENTITY, ttl_seconds=3600, negative_ttl_seconds=30)


class UserTenantRepositoryMixin:
    """User / tenant / membership CRUD with tenant-scoped cache."""

    db: AsyncSession

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
