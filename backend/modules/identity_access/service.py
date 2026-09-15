"""Identity service facade — auth, roles, and credential flows."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.identity_access.auth_credentials import AuthCredentialsMixin
from backend.modules.identity_access.auth_sessions import AuthSessionsMixin
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.identity_access.system_roles import (
    DEFAULT_PERMISSIONS,
    SYSTEM_ROLES,
    SystemRolesMixin,
    _hash_token,
    hash_token,
)

__all__ = [
    "DEFAULT_PERMISSIONS",
    "SYSTEM_ROLES",
    "IdentityService",
    "_hash_token",
    "hash_token",
]


class IdentityService(SystemRolesMixin, AuthSessionsMixin, AuthCredentialsMixin):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IdentityRepository(db)
        self.audit = AuditService(db)
