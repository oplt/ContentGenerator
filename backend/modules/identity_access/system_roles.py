"""System roles, permissions, and membership response helpers."""

from __future__ import annotations

import hashlib
from typing import Any

from backend.core.config import settings
from backend.modules.identity_access.models import Role, TenantUser, User
from backend.modules.identity_access.schemas import (
    AuthUserResponse,
    MembershipResponse,
    MembershipRoleResponse,
)

DEFAULT_PERMISSIONS: list[tuple[str, str, str]] = [
    ("sources:read", "View source configurations", "sources"),
    ("sources:write", "Manage source configurations", "sources"),
    ("stories:read", "View story clusters", "stories"),
    ("briefs:write", "Generate and action editorial briefs", "briefs"),
    ("content:write", "Generate and revise content", "content"),
    ("approvals:read", "View approval state", "approvals"),
    ("publishing:write", "Publish content to social platforms", "publishing"),
    ("analytics:read", "View analytics dashboards", "analytics"),
    ("settings:write", "Manage tenant and brand settings", "settings"),
    ("audit:read", "View audit logs", "audit"),
]

SYSTEM_ROLES: dict[str, tuple[str, list[str]]] = {
    "owner": (
        "Workspace Owner",
        [permission[0] for permission in DEFAULT_PERMISSIONS],
    ),
    "editor": (
        "Content Editor",
        [
            "sources:read",
            "stories:read",
            "briefs:write",
            "content:write",
            "approvals:read",
            "publishing:write",
            "analytics:read",
        ],
    ),
    "analyst": (
        "Analyst",
        [
            "sources:read",
            "stories:read",
            "analytics:read",
            "audit:read",
        ],
    ),
}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Historical private-name alias.
_hash_token = hash_token


class SystemRolesMixin:
    """Bootstrap system roles/permissions and build auth membership payloads."""

    repo: Any
    db: Any

    async def ensure_system_roles_and_permissions(self) -> None:
        for code, description, category in DEFAULT_PERMISSIONS:
            if not await self.repo.get_permission_by_code(code):
                await self.repo.create_permission(
                    code=code,
                    description=description,
                    category=category,
                )

        for slug, (name, permission_codes) in SYSTEM_ROLES.items():
            role = await self.repo.get_role(tenant_id=None, slug=slug)
            if role:
                role.permission_codes = permission_codes
                role.name = name
            else:
                await self.repo.create_role(
                    tenant_id=None,
                    name=name,
                    slug=slug,
                    description=f"System role {name}",
                    is_system=True,
                    permission_codes=permission_codes,
                )
        await self.db.flush()

    async def _get_system_role(self, slug: str) -> Role:
        role = await self.repo.get_role(tenant_id=None, slug=slug)
        if not role:
            await self.ensure_system_roles_and_permissions()
            role = await self.repo.get_role(tenant_id=None, slug=slug)
        if not role:
            raise RuntimeError(f"system role {slug} missing")
        return role

    async def _build_membership_responses(
        self, memberships: list[TenantUser]
    ) -> list[MembershipResponse]:
        responses: list[MembershipResponse] = []
        for membership in memberships:
            tenant = await self.repo.get_tenant_by_id(membership.tenant_id)
            if not tenant:
                continue
            role = membership.role
            responses.append(
                MembershipResponse(
                    tenant_id=tenant.id,
                    tenant_name=tenant.name,
                    tenant_slug=tenant.slug,
                    role=MembershipRoleResponse(
                        id=role.id if role else None,
                        name=role.name if role else None,
                        slug=role.slug if role else None,
                        permission_codes=role.permission_codes if role else [],
                    ),
                    status=str(membership.membership_status),
                )
            )
        return responses

    async def build_auth_user(self, user: User) -> AuthUserResponse:
        memberships = await self.repo.list_user_memberships(user.id)
        return AuthUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_verified=user.is_verified or not settings.SEND_AUTH_EMAIL_ON_SIGNUP,
            is_admin=user.is_admin,
            mfa_enabled=user.mfa_enabled,
            default_tenant_id=user.default_tenant_id,
            memberships=await self._build_membership_responses(memberships),
        )
