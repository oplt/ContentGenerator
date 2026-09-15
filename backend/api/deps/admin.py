"""Admin/owner dependency helpers used only by quarantined dormant routers.

Live product authorization uses ``backend.api.deps.auth`` and module-local
permission checks. Do not wire these helpers into newly activated routes without
completing the dormant capability checklist in ``docs/dormant-modules.md``.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from backend.api.deps.auth import get_current_membership, get_current_user
from backend.core.config import settings
from backend.modules.identity_access.models import TenantUser, User


async def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    if settings.MFA_ACCESS and not current_user.mfa_enabled:
        raise HTTPException(status_code=403, detail="Admin MFA required")
    return current_user


async def get_owner_membership(membership: TenantUser = Depends(get_current_membership)) -> TenantUser:
    if membership.role and membership.role.slug == "owner":
        return membership
    raise HTTPException(status_code=403, detail="Owner access required")
