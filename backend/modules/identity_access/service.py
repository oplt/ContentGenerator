from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.time_utils import as_utc, utc_now
from backend.core.security import (
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.modules.audit.service import AuditService
from backend.modules.identity_access.models import Role, TenantUser, User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.identity_access.schemas import (
    AuthUserResponse,
    MembershipResponse,
    MembershipRoleResponse,
)
from backend.workers.email import queue_email


DEFAULT_PERMISSIONS: list[tuple[str, str, str]] = [
    ("sources:read", "View source configurations", "sources"),
    ("sources:write", "Manage source configurations", "sources"),
    ("stories:read", "View story clusters", "stories"),
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IdentityRepository(db)
        self.audit = AuditService(db)

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

    async def _build_membership_responses(self, memberships: list[TenantUser]) -> list[MembershipResponse]:
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
            is_verified=user.is_verified,
            is_admin=user.is_admin,
            mfa_enabled=user.mfa_enabled,
            default_tenant_id=user.default_tenant_id,
            memberships=await self._build_membership_responses(memberships),
        )

    async def sign_up(
        self,
        email: str,
        password: str,
        full_name: str | None,
        admin_invite_code: str | None = None,
    ) -> User:
        normalized_email = email.lower()
        existing = await self.repo.get_user_by_email(normalized_email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        invite_code = (admin_invite_code or "").strip()
        configured_invite_code = settings.ADMIN_SIGNUP_INVITE_CODE.strip()
        is_admin = False
        if invite_code:
            if not configured_invite_code or not secrets.compare_digest(
                invite_code, configured_invite_code
            ):
                raise HTTPException(status_code=403, detail="Invalid admin invite code")
            is_admin = True

        await self.ensure_system_roles_and_permissions()
        user = await self.repo.create_user(
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name,
            is_admin=is_admin,
        )

        tenant_name = f"{full_name or normalized_email.split('@', maxsplit=1)[0]}'s workspace"
        base_slug = slugify(full_name or normalized_email.split("@", maxsplit=1)[0]) or "workspace"
        slug = base_slug
        suffix = 1
        while await self.repo.get_tenant_by_slug(slug):
            suffix += 1
            slug = f"{base_slug}-{suffix}"
        tenant = await self.repo.create_tenant(name=tenant_name, slug=slug)
        owner_role = await self._get_system_role("owner")
        await self.repo.create_membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=owner_role,
            title="Owner",
        )
        user.default_tenant_id = tenant.id
        await self.db.commit()
        await self.db.refresh(user)

        token = await self._store_verification_token(user.id)
        verification_link = (
            f"{settings.FRONTEND_URL}/verify-email?{urlencode({'token': token, 'email': user.email})}"
        )
        queue_email(
            to=user.email,
            subject=f"Verify your {settings.APP_NAME} email",
            html_body=(
                "<p>Welcome to SignalForge.</p>"
                f"<p>Verify your email: <a href=\"{verification_link}\">{verification_link}</a></p>"
            ),
            text_body=f"Verify your email: {verification_link}",
        )
        await self.audit.record(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="identity.user_signed_up",
            entity_type="user",
            entity_id=str(user.id),
            message="User registered and default tenant created",
            payload={"tenant_id": str(tenant.id)},
        )
        await self.db.commit()
        return user

    async def sign_in(self, email: str, password: str) -> dict[str, object]:
        user = await self.repo.get_user_by_email(email.lower())
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")

        raw_refresh = generate_refresh_token()
        expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        await self.repo.create_refresh_session(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=expires_at,
        )
        await self.audit.record(
            tenant_id=user.default_tenant_id,
            actor_user_id=user.id,
            action="identity.user_signed_in",
            entity_type="user",
            entity_id=str(user.id),
            message="User signed in",
        )
        await self.db.commit()
        return {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": raw_refresh,
            "user": user,
        }

    async def refresh(self, raw_refresh_token: str) -> dict[str, object]:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)
        if not session or session.is_revoked:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if as_utc(session.expires_at) < utc_now():
            raise HTTPException(status_code=401, detail="Refresh token expired")

        user = await self.repo.get_user_by_id(session.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or disabled")

        await self.repo.revoke_refresh_session(session)
        new_raw = generate_refresh_token()
        new_expires = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.repo.create_refresh_session(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw),
            expires_at=new_expires,
        )
        await self.db.commit()
        return {
            "access_token": create_access_token(str(user.id)),
            "refresh_token": new_raw,
            "user": user,
        }

    async def logout(self, raw_refresh_token: str) -> None:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)
        if session:
            await self.repo.revoke_refresh_session(session)
            await self.db.commit()

    async def _store_verification_token(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(32)
        key = f"verify:{_hash_token(token)}"
        await redis_client.setex(key, settings.VERIFICATION_TOKEN_TTL, str(user_id))
        return token

    async def verify_email(self, token: str) -> None:
        key = f"verify:{_hash_token(token)}"
        user_id = await redis_client.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired verification token")
        user = await self.repo.get_user_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_verified = True
        await redis_client.delete(key)
        await self.db.commit()

    async def resend_verification(self, email: str) -> None:
        user = await self.repo.get_user_by_email(email.lower())
        if not user or user.is_verified:
            return
        token = await self._store_verification_token(user.id)
        verification_link = (
            f"{settings.FRONTEND_URL}/verify-email?{urlencode({'token': token, 'email': user.email})}"
        )
        queue_email(
            to=user.email,
            subject=f"Verify your {settings.APP_NAME} email",
            html_body=f"<p>Verify your email: <a href=\"{verification_link}\">{verification_link}</a></p>",
            text_body=f"Verify your email: {verification_link}",
        )

    async def forgot_password(self, email: str) -> None:
        user = await self.repo.get_user_by_email(email.lower())
        if not user:
            return
        token = secrets.token_urlsafe(32)
        key = f"pwd_reset:{_hash_token(token)}"
        await redis_client.setex(key, settings.PASSWORD_RESET_TOKEN_TTL, str(user.id))
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        queue_email(
            to=user.email,
            subject=f"Reset your {settings.APP_NAME} password",
            html_body=f"<p>Reset password: <a href=\"{reset_link}\">{reset_link}</a></p>",
            text_body=f"Reset password: {reset_link}",
        )

    async def reset_password(self, token: str, new_password: str) -> None:
        key = f"pwd_reset:{_hash_token(token)}"
        user_id = await redis_client.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        user = await self.repo.get_user_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = hash_password(new_password)
        await redis_client.delete(key)
        # Invalidate all existing sessions so stolen refresh tokens cannot be reused.
        for session in await self.repo.list_active_sessions(user.id):
            await self.repo.revoke_refresh_session(session)
        await self.db.commit()

    async def mfa_enable(self, user: User) -> dict[str, str]:
        import pyotp

        secret = pyotp.random_base32()
        key = f"mfa_pending:{user.id}"
        await redis_client.setex(key, 600, secret)
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)
        return {"secret": secret, "provisioning_uri": uri}

    async def mfa_verify_enable(self, user: User, code: str) -> None:
        import pyotp

        key = f"mfa_pending:{user.id}"
        secret = await redis_client.get(key)
        if not secret:
            raise HTTPException(status_code=400, detail="MFA setup session expired")
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")
        user.mfa_secret = encrypt_secret(secret)
        user.mfa_enabled = True
        await redis_client.delete(key)
        await self.db.commit()

    async def mfa_disable(self, user: User, code: str) -> None:
        import pyotp

        if not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA is not enabled")
        raw_secret = decrypt_secret(user.mfa_secret)
        if not pyotp.TOTP(raw_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")
        user.mfa_enabled = False
        user.mfa_secret = None
        await self.db.commit()
