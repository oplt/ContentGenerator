from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_cache
from backend.core.time_utils import as_utc, utc_now, utc_now_naive
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

class IdentityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        # Try to get from cache first
        cache_key = f"user_by_email:{email.lower()}"
        cached_user = await redis_cache.get(cache_key)
        if cached_user is not None:
            return User(**cached_user)

        # If not in cache, get from database
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        
        # Cache the result if found
        if user:
            await redis_cache.set(cache_key, user.model_dump(), expire=3600)  # Cache for 1 hour
        
        return user

    async def get_user_by_id(self, user_id: uuid.UUID | str) -> User | None:
        # Try to get from cache first
        cache_key = f"user_by_id:{user_id}"
        cached_user = await redis_cache.get(cache_key)
        if cached_user is not None:
            return User(**cached_user)

        # If not in cache, get from database
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        # Cache the result if found
        if user:
            await redis_cache.set(cache_key, user.model_dump(), expire=3600)  # Cache for 1 hour
        
        return user

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
        
        # Invalidate cache for this user
        cache_key_email = f"user_by_email:{email.lower()}"
        cache_key_id = f"user_by_id:{user.id}"
        await redis_cache.delete(cache_key_email)
        await redis_cache.delete(cache_key_id)
        
        return user

    async def create_tenant(self, *, name: str, slug: str) -> Tenant:
        tenant = Tenant(name=name, slug=slug, status=TenantStatus.TRIAL.value)
        self.db.add(tenant)
        await self.db.flush()
        
        # Invalidate cache for tenant by slug
        cache_key_slug = f"tenant_by_slug:{slug}"
        cache_key_id = f"tenant_by_id:{tenant.id}"
        await redis_cache.delete(cache_key_slug)
        await redis_cache.delete(cache_key_id)
        
        return tenant

    async def get_tenant_by_id(self, tenant_id: uuid.UUID | str) -> Tenant | None:
        # Try to get from cache first
        cache_key = f"tenant_by_id:{tenant_id}"
        cached_tenant = await redis_cache.get(cache_key)
        if cached_tenant is not None:
            return Tenant(**cached_tenant)

        # If not in cache, get from database
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        
        # Cache the result if found
        if tenant:
            await redis_cache.set(cache_key, tenant.model_dump(), expire=3600)  # Cache for 1 hour
        
        return tenant

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        # Try to get from cache first
        cache_key = f"tenant_by_slug:{slug}"
        cached_tenant = await redis_cache.get(cache_key)
        if cached_tenant is not None:
            return Tenant(**cached_tenant)

        # If not in cache, get from database
        result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()
        
        # Cache the result if found
        if tenant:
            await redis_cache.set(cache_key, tenant.model_dump(), expire=3600)  # Cache for 1 hour
        
        return tenant

    from sqlalchemy.orm import selectinload

    async def list_user_memberships(self, user_id: uuid.UUID | str) -> list[TenantUser]:
        # Try to get from cache first
        cache_key = f"user_memberships:{user_id}"
        cached_memberships = await redis_cache.get(cache_key)
        if cached_memberships is not None:
            return [TenantUser(**membership) for membership in cached_memberships]

        # If not in cache, get from database
        result = await self.db.execute(
            select(TenantUser)
            .options(selectinload(TenantUser.role)) # Eagerly load the role
            .where(
                TenantUser.user_id == user_id,
                TenantUser.membership_status == MembershipStatus.ACTIVE.value,
                TenantUser.deleted_at.is_(None),
            )
            .order_by(TenantUser.created_at.asc())
        )
        memberships = list(result.scalars().all())
        
        # Cache the result
        if memberships:
            await redis_cache.set(cache_key, [membership.model_dump() for membership in memberships], expire=1800)  # Cache for 30 minutes
        
        return memberships

    async def get_membership(
        self, *, user_id: uuid.UUID | str, tenant_id: uuid.UUID | str
    ) -> TenantUser | None:
        # Try to get from cache first
        cache_key = f"membership:{user_id}:{tenant_id}"
        cached_membership = await redis_cache.get(cache_key)
        if cached_membership is not None:
            return TenantUser(**cached_membership)

        # If not in cache, get from database
        result = await self.db.execute(
            select(TenantUser)
            .options(selectinload(TenantUser.role))
            .where(
                TenantUser.user_id == user_id,
                TenantUser.tenant_id == tenant_id,
                TenantUser.deleted_at.is_(None),
            )
        )
        membership = result.scalar_one_or_none()
        
        # Cache the result if found
        if membership:
            await redis_cache.set(cache_key, membership.model_dump(), expire=1800)  # Cache for 30 minutes
        
        return membership

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
        
        # Invalidate cache for user's memberships
        cache_key_memberships = f"user_memberships:{user_id}"
        await redis_cache.delete(cache_key_memberships)
        
        # Invalidate cache for this specific membership
        cache_key_membership = f"membership:{user_id}:{tenant_id}"
        await redis_cache.delete(cache_key_membership)
        
        return membership

    async def list_permissions(self) -> list[Permission]:
        # Try to get from cache first
        cache_key = "all_permissions"
        cached_permissions = await redis_cache.get(cache_key)
        if cached_permissions is not None:
            return [Permission(**permission) for permission in cached_permissions]

        # If not in cache, get from database
        result = await self.db.execute(select(Permission).order_by(Permission.code.asc()))
        permissions = list(result.scalars().all())
        
        # Cache the result
        if permissions:
            await redis_cache.set(cache_key, [permission.model_dump() for permission in permissions], expire=3600)  # Cache for 1 hour
        
        return permissions

    async def get_permission_by_code(self, code: str) -> Permission | None:
        # Try to get from cache first
        cache_key = f"permission_by_code:{code}"
        cached_permission = await redis_cache.get(cache_key)
        if cached_permission is not None:
            return Permission(**cached_permission)

        # If not in cache, get from database
        result = await self.db.execute(select(Permission).where(Permission.code == code))
        permission = result.scalar_one_or_none()
        
        # Cache the result if found
        if permission:
            await redis_cache.set(cache_key, permission.model_dump(), expire=3600)  # Cache for 1 hour
        
        return permission

    async def create_permission(self, *, code: str, description: str, category: str) -> Permission:
        permission = Permission(code=code, description=description, category=category)
        self.db.add(permission)
        await self.db.flush()
        
        # Invalidate cache for all permissions
        cache_key_all = "all_permissions"
        await redis_cache.delete(cache_key_all)
        
        # Invalidate cache for this specific permission
        cache_key_code = f"permission_by_code:{code}"
        await redis_cache.delete(cache_key_code)
        
        return permission

    async def get_role(self, *, tenant_id: uuid.UUID | None, slug: str) -> Role | None:
        # Try to get from cache first
        cache_key = f"role:{tenant_id}:{slug}"
        cached_role = await redis_cache.get(cache_key)
        if cached_role is not None:
            return Role(**cached_role)

        # If not in cache, get from database
        result = await self.db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.slug == slug)
        )
        role = result.scalar_one_or_none()
        
        # Cache the result if found
        if role:
            await redis_cache.set(cache_key, role.model_dump(), expire=3600)  # Cache for 1 hour
        
        return role

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
        
        # Invalidate cache for this role
        cache_key = f"role:{tenant_id}:{slug}"
        await redis_cache.delete(cache_key)
        
        # Invalidate cache for all permissions if system role
        if is_system:
            cache_key_permissions = "all_permissions"
            await redis_cache.delete(cache_key_permissions)
        
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
        
        # Invalidate user's active sessions cache
        cache_key_sessions = f"active_sessions:{user_id}"
        await redis_cache.delete(cache_key_sessions)
        
        return session

    async def get_refresh_session_by_hash(self, token_hash: str) -> RefreshSession | None:
        # Try to get from cache first
        cache_key = f"refresh_session_by_hash:{token_hash}"
        cached_session = await redis_cache.get(cache_key)
        if cached_session is not None:
            return RefreshSession(**cached_session)

        # If not in cache, get from database
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        
        # Cache the result if found
        if session:
            await redis_cache.set(cache_key, session.model_dump(), expire=3600)  # Cache for 1 hour
        
        return session

    async def get_session_by_id(self, session_id: uuid.UUID | str) -> RefreshSession | None:
        # Try to get from cache first
        cache_key = f"refresh_session_by_id:{session_id}"
        cached_session = await redis_cache.get(cache_key)
        if cached_session is not None:
            return RefreshSession(**cached_session)

        # If not in cache, get from database
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        
        # Cache the result if found
        if session:
            await redis_cache.set(cache_key, session.model_dump(), expire=3600)  # Cache for 1 hour
        
        return session

    async def revoke_refresh_session(self, session: RefreshSession) -> None:
        session.is_revoked = True
        await self.db.flush()
        
        # Invalidate cache for this session
        cache_key_hash = f"refresh_session_by_hash:{session.token_hash}"
        cache_key_id = f"refresh_session_by_id:{session.id}"
        await redis_cache.delete(cache_key_hash)
        await redis_cache.delete(cache_key_id)
        
        # Invalidate user's active sessions cache
        cache_key_sessions = f"active_sessions:{session.user_id}"
        await redis_cache.delete(cache_key_sessions)

    async def list_active_sessions(self, user_id: uuid.UUID) -> list[RefreshSession]:
        # Try to get from cache first
        cache_key = f"active_sessions:{user_id}"
        cached_sessions = await redis_cache.get(cache_key)
        if cached_sessions is not None:
            return [RefreshSession(**session) for session in cached_sessions]

        # If not in cache, get from database
        result = await self.db.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > utc_now_naive(),
            )
        )
        sessions = list(result.scalars().all())
        
        # Cache the result
        if sessions:
            await redis_cache.set(cache_key, [session.model_dump() for session in sessions], expire=300)  # Cache for 5 minutes
        
        return sessions

class TenantRepository:
    """Thin wrapper for tenant-level queries used by workers."""

    def __init__(self, db: "AsyncSession") -> None:
        from sqlalchemy.ext.asyncio import AsyncSession as _AS # noqa: F401
        self.db = db

    async def list_active_tenants(self) -> list["Tenant"]:
        """Return all non-suspended tenants for beat-scheduled fan-out tasks."""
        from sqlalchemy import select
        from backend.modules.identity_access.models import Tenant, TenantStatus
        
        # Try to get from cache first
        cache_key = "active_tenants"
        cached_tenants = await redis_cache.get(cache_key)
        if cached_tenants is not None:
            return [Tenant(**tenant) for tenant in cached_tenants]

        result = await self.db.execute(
            select(Tenant).where(
                Tenant.status != TenantStatus.SUSPENDED.value,
                Tenant.deleted_at.is_(None),
            )
        )
        tenants = list(result.scalars().all())
        
        # Cache the result
        if tenants:
            await redis_cache.set(cache_key, [tenant.model_dump() for tenant in tenants], expire=600)  # Cache for 10 minutes
        
        return tenants

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
        return membership

    async def list_permissions(self) -> list[Permission]:
        result = await self.db.execute(select(Permission).order_by(Permission.code.asc()))
        return list(result.scalars().all())

    async def get_permission_by_code(self, code: str) -> Permission | None:
        result = await self.db.execute(select(Permission).where(Permission.code == code))
        return result.scalar_one_or_none()

    async def create_permission(self, *, code: str, description: str, category: str) -> Permission:
        permission = Permission(code=code, description=description, category=category)
        self.db.add(permission)
        await self.db.flush()
        return permission

    async def get_role(self, *, tenant_id: uuid.UUID | None, slug: str) -> Role | None:
        result = await self.db.execute(
            select(Role).where(Role.tenant_id == tenant_id, Role.slug == slug)
        )
        return result.scalar_one_or_none()

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
        return session

    async def get_refresh_session_by_hash(self, token_hash: str) -> RefreshSession | None:
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_session_by_id(self, session_id: uuid.UUID | str) -> RefreshSession | None:
        result = await self.db.execute(
            select(RefreshSession).where(RefreshSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_session(self, session: RefreshSession) -> None:
        session.is_revoked = True
        await self.db.flush()

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

    def __init__(self, db: "AsyncSession") -> None:
        from sqlalchemy.ext.asyncio import AsyncSession as _AS  # noqa: F401
        self.db = db

    async def list_active_tenants(self) -> list["Tenant"]:
        """Return all non-suspended tenants for beat-scheduled fan-out tasks."""
        from sqlalchemy import select
        from backend.modules.identity_access.models import Tenant, TenantStatus
        result = await self.db.execute(
            select(Tenant).where(
                Tenant.status != TenantStatus.SUSPENDED.value,
                Tenant.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())
