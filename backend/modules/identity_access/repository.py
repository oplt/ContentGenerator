from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload  
from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            is_admin=is_admin,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def create_tenant(self, *, name: str, slug: str) -> Tenant:
        tenant = Tenant(name=name, slug=slug, status=TenantStatus.TRIAL.value)
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def get_tenant_by_id(self, tenant_id: uuid.UUID | str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.slug == slug))
        return result.scalar_one_or_none()

    from sqlalchemy.orm import selectinload

    async def list_user_memberships(self, user_id: uuid.UUID | str) -> list[TenantUser]:
        result = await self.db.execute(
            select(TenantUser)
            .options(selectinload(TenantUser.role))  # Eagerly load the role
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
        # Convert timezone-aware datetime to naive UTC if it has timezone info
        if expires_at.tzinfo is not None:
            # Convert to UTC and remove timezone info
            expires_at_naive = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            expires_at_naive = expires_at

        session = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at_naive
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
        # Use naive UTC datetime for comparison since database stores naive UTC
        now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        result = await self.db.execute(
            select(RefreshSession).where(
                RefreshSession.user_id == user_id,
                RefreshSession.is_revoked.is_(False),
                RefreshSession.expires_at > now_naive,
                )
        )
        return list(result.scalars().all())
