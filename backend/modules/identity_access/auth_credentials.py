"""Signup, email verification, password reset, and MFA flows."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import HTTPException
from slugify import slugify

from backend.core.cache import redis_cache
from backend.core.config import settings
from backend.core.security import encrypt_secret, hash_password
from backend.core.tenant_cache import OWNER_AUTH_TOKEN, build_cache_key
from backend.modules.identity_access.models import User
from backend.modules.identity_access.system_roles import hash_token
from backend.workers.email import queue_email


class AuthCredentialsMixin:
    """Account provisioning and credential recovery flows."""

    repo: Any
    db: Any
    audit: Any

    async def sign_up(
        self,
        email: str,
        password: str,
        full_name: str | None,
        admin_invite_code: str | None = None,
    ) -> User | None:
        normalized_email = email.lower()
        existing = await self.repo.get_user_by_email(normalized_email)
        if existing:
            if not existing.is_verified:
                await self.resend_verification(normalized_email)
            return None

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
            is_verified=not settings.SEND_AUTH_EMAIL_ON_SIGNUP,
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

        if settings.SEND_AUTH_EMAIL_ON_SIGNUP:
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

    async def _store_verification_token(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(32)
        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"verify:{hash_token(token)}",
        )
        await redis_cache.setex(key, settings.VERIFICATION_TOKEN_TTL, str(user_id))
        return token

    async def verify_email(self, token: str) -> None:
        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"verify:{hash_token(token)}",
        )
        user_id = await redis_cache.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired verification token")
        user = await self.repo.get_user_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_verified = True
        await redis_cache.delete(key)
        await self.db.commit()

    async def resend_verification(self, email: str) -> None:
        user = await self.repo.get_user_by_email(email.lower())
        if not user or user.is_verified:
            return
        if not settings.SEND_AUTH_EMAIL_ON_SIGNUP:
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
        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"pwd_reset:{hash_token(token)}",
        )
        await redis_cache.setex(key, settings.PASSWORD_RESET_TOKEN_TTL, str(user.id))
        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        queue_email(
            to=user.email,
            subject=f"Reset your {settings.APP_NAME} password",
            html_body=f"<p>Reset password: <a href=\"{reset_link}\">{reset_link}</a></p>",
            text_body=f"Reset password: {reset_link}",
        )

    async def reset_password(self, token: str, new_password: str) -> None:
        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"pwd_reset:{hash_token(token)}",
        )
        user_id = await redis_cache.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        user = await self.repo.get_user_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = hash_password(new_password)
        await redis_cache.delete(key)
        # Invalidate all existing sessions so stolen refresh tokens cannot be reused.
        for session in await self.repo.list_active_sessions(user.id):
            await self.repo.revoke_refresh_session(session)
        await self.db.commit()

    async def mfa_enable(self, user: User) -> dict[str, str]:
        import pyotp

        secret = pyotp.random_base32()
        # Enrollment handshake only (600s). Not a general credential cache.
        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"mfa_pending:{user.id}",
        )
        await redis_cache.setex(key, 600, secret)
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)
        return {"secret": secret, "provisioning_uri": uri}

    async def mfa_verify_enable(self, user: User, code: str) -> None:
        import pyotp

        key = build_cache_key(
            owner=OWNER_AUTH_TOKEN,
            global_scope=True,
            identity=f"mfa_pending:{user.id}",
        )
        secret = await redis_cache.get(key)
        if not secret:
            raise HTTPException(status_code=400, detail="MFA setup session expired")
        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")
        user.mfa_secret = encrypt_secret(secret)
        user.mfa_enabled = True
        await redis_cache.delete(key)
        await self.db.commit()

    async def mfa_disable(self, user: User, code: str) -> None:
        import pyotp

        from backend.core.security import decrypt_secret

        if not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA is not enabled")
        raw_secret = decrypt_secret(user.mfa_secret)
        if not pyotp.TOTP(raw_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")
        user.mfa_enabled = False
        user.mfa_secret = None
        await self.db.commit()
