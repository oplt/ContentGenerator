"""Identity repository facade — users, RBAC, sessions, and tenant listing."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.repository_rbac import RbacRepositoryMixin
from backend.modules.identity_access.repository_sessions import (
    SessionRepositoryMixin,
    TenantRepository,
)
from backend.modules.identity_access.repository_users import UserTenantRepositoryMixin

__all__ = [
    "IdentityAccessRepository",
    "IdentityRepository",
    "TenantRepository",
]


class IdentityRepository(
    UserTenantRepositoryMixin,
    RbacRepositoryMixin,
    SessionRepositoryMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db


# Compatibility alias used by publishing orchestration.
IdentityAccessRepository = IdentityRepository
