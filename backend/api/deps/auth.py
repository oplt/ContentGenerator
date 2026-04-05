from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.db import get_db
from backend.core.security import decode_token
from backend.modules.identity_access.models import Tenant, TenantUser, User
from backend.modules.identity_access.repository import IdentityRepository

bearer_scheme = HTTPBearer()


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload["sub"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    repo = IdentityRepository(db)
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_current_membership(
    current_user: User = Depends(get_current_user),
    tenant_id_header: str | None = Header(default=None, alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_db),
) -> TenantUser:
    repo = IdentityRepository(db)
    tenant_id = tenant_id_header or (str(current_user.default_tenant_id) if current_user.default_tenant_id else None)
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="No active tenant selected")
    membership = await repo.get_membership(user_id=current_user.id, tenant_id=UUID(tenant_id))
    if not membership:
        raise HTTPException(status_code=403, detail="No access to tenant")
    return membership


async def get_current_tenant(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    repo = IdentityRepository(db)
    tenant = await repo.get_tenant_by_id(membership.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def require_permission(permission_code: str) -> Callable[..., TenantUser]:
    async def dependency(membership: TenantUser = Depends(get_current_membership)) -> TenantUser:
        if membership.role and permission_code in membership.role.permission_codes:
            return membership
        raise HTTPException(status_code=403, detail="Missing required permission")

    return dependency
