from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.db import get_db
from backend.core.security import decode_token, verify_csrf_token
from backend.core.time_utils import as_utc, utc_now
from backend.modules.identity_access.models import Tenant, TenantUser, User
from backend.modules.identity_access.repository import IdentityRepository

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def get_current_user(
        request: Request,
        access_token: str | None = Cookie(default=None),
        csrf_token: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        db: AsyncSession = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    if request.method not in _SAFE_METHODS and not verify_csrf_token(csrf_token, x_csrf_token):
        raise HTTPException(status_code=403, detail="CSRF verification failed")
    try:
        payload = decode_token(access_token)
        user_id = payload["sub"]
        session_id = payload["sid"]
        token_type = payload["type"]
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if token_type != "access":
        raise HTTPException(status_code=401, detail="Invalid token")

    repo = IdentityRepository(db)
    session = await repo.get_session_by_id(session_id)
    if not session or session.is_revoked or as_utc(session.expires_at) < utc_now():
        raise HTTPException(status_code=401, detail="Session expired")
    user = await repo.get_user_by_id(user_id)
    if not user or session.user_id != user.id or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_verified and not request.url.path.startswith("/api/v1/auth/"):
        raise HTTPException(status_code=403, detail="Email verification required")

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
