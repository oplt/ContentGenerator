import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.modules.identity_access.models import User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.platform.service import PlatformService
from backend.workers.email import queue_email


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class IdentityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = IdentityRepository(db)

    async def _get_platform_app_name(self) -> str:
        platform_service = PlatformService(self.db)
        config = await platform_service.get_platform_config()
        return config.app_name

    # ------------------------------------------------------------------ sign up / sign in

    async def sign_up(
        self,
        email: str,
        password: str,
        full_name: str | None,
        admin_invite_code: str | None = None,
    ) -> User:
        existing = await self.repo.get_user_by_email(email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        invite_code = (admin_invite_code or "").strip()
        configured_invite_code = settings.ADMIN_SIGNUP_INVITE_CODE.strip()
        is_admin = False
        if invite_code:
            if not configured_invite_code or not secrets.compare_digest(invite_code, configured_invite_code):
                raise HTTPException(status_code=403, detail="Invalid admin invite code")
            is_admin = True

        user = await self.repo.create_user(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            is_admin=is_admin,
        )
        await self.db.commit()
        await self.db.refresh(user)

        # queue verification email (fire-and-forget)
        token = await self._store_verification_token(user.id)
        verification_link = f"{settings.FRONTEND_URL}/verify-email?{urlencode({'token': token, 'email': user.email})}"
        platform_service = PlatformService(self.db)
        app_name = await self._get_platform_app_name()
        subject, html_body, text_body = await platform_service.render_email_template(
            key="auth.verify_email",
            context={
                "app_name": app_name,
                "recipient_email": user.email,
                "action_url": verification_link,
            },
            fallback_subject="Verify your email address",
            fallback_html=(
                "<p>Thanks for signing up. Click the link below to verify your email:</p>"
                f"<p><a href=\"{verification_link}\">{verification_link}</a></p>"
                "<p>This link expires in 24 hours.</p>"
            ),
            fallback_text=(
                "Thanks for signing up.\n"
                f"Verify your email: {verification_link}\n"
                "This link expires in 24 hours."
            ),
        )
        queue_email(
            to=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

        return user

    async def sign_in(self, email: str, password: str) -> dict:
        user = await self.repo.get_user_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")

        raw_refresh = generate_refresh_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        await self.repo.create_refresh_session(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=expires_at,
        )
        await self.db.commit()

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": raw_refresh,
            "user": user,
        }

    async def refresh(self, raw_refresh_token: str) -> dict:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)

        if not session or session.is_revoked:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if session.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Refresh token expired")

        user = await self.repo.get_user_by_id(session.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or disabled")

        await self.repo.revoke_refresh_session(session)

        new_raw = generate_refresh_token()
        new_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        await self.repo.create_refresh_session(user.id, hash_refresh_token(new_raw), new_expires)
        await self.db.commit()

        return {
            "access_token": create_access_token(user.id),
            "refresh_token": new_raw,
            "user": user,
        }

    async def logout(self, raw_refresh_token: str) -> None:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)
        if session:
            await self.repo.revoke_refresh_session(session)
            await self.db.commit()

    # ------------------------------------------------------------------ email verification

    async def _store_verification_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        key = f"verify:{_hash_token(token)}"
        await redis_client.setex(key, settings.VERIFICATION_TOKEN_TTL, user_id)
        return token

    async def verify_email(self, token: str) -> None:
        key = f"verify:{_hash_token(token)}"
        user_id = await redis_client.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired verification token")

        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_verified = True
        await self.db.commit()
        await redis_client.delete(key)

    async def resend_verification(self, email: str) -> None:
        user = await self.repo.get_user_by_email(email)
        if not user or user.is_verified:
            # Don't leak whether address exists
            return

        token = await self._store_verification_token(user.id)
        verification_link = f"{settings.FRONTEND_URL}/verify-email?{urlencode({'token': token, 'email': user.email})}"
        platform_service = PlatformService(self.db)
        app_name = await self._get_platform_app_name()
        subject, html_body, text_body = await platform_service.render_email_template(
            key="auth.verify_email",
            context={
                "app_name": app_name,
                "recipient_email": user.email,
                "action_url": verification_link,
            },
            fallback_subject="Verify your email address",
            fallback_html=(
                "<p>Thanks for signing up. Click the link below to verify your email:</p>"
                f"<p><a href=\"{verification_link}\">{verification_link}</a></p>"
                "<p>This link expires in 24 hours.</p>"
            ),
            fallback_text=(
                "Thanks for signing up.\n"
                f"Verify your email: {verification_link}\n"
                "This link expires in 24 hours."
            ),
        )
        queue_email(
            to=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    # ------------------------------------------------------------------ password reset

    async def forgot_password(self, email: str) -> None:
        user = await self.repo.get_user_by_email(email)
        if not user:
            return  # silent — don't leak whether address exists

        token = secrets.token_urlsafe(32)
        key = f"pwd_reset:{_hash_token(token)}"
        await redis_client.setex(key, settings.PASSWORD_RESET_TOKEN_TTL, user.id)

        reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        platform_service = PlatformService(self.db)
        app_name = await self._get_platform_app_name()
        subject, html_body, text_body = await platform_service.render_email_template(
            key="auth.reset_password",
            context={
                "app_name": app_name,
                "recipient_email": user.email,
                "action_url": reset_link,
            },
            fallback_subject="Reset your password",
            fallback_html=(
                "<p>We received a request to reset your password. Click the link below:</p>"
                f"<p><a href=\"{reset_link}\">{reset_link}</a></p>"
                "<p>This link expires in 1 hour. If you did not request this, ignore this email.</p>"
            ),
            fallback_text=(
                "We received a request to reset your password.\n"
                f"Reset link: {reset_link}\n"
                "This link expires in 1 hour. If you did not request this, ignore this email."
            ),
        )
        queue_email(
            to=user.email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
        )

    async def reset_password(self, token: str, new_password: str) -> None:
        key = f"pwd_reset:{_hash_token(token)}"
        user_id = await redis_client.get(key)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.password_hash = hash_password(new_password)
        await self.db.commit()
        await redis_client.delete(key)

    # ------------------------------------------------------------------ MFA (TOTP)

    async def mfa_enable(self, user: User) -> dict:
        try:
            import pyotp
        except ImportError:
            raise HTTPException(status_code=501, detail="MFA not available (pyotp not installed)")

        secret = pyotp.random_base32()
        # Store temporarily until the user verifies with the first TOTP code
        key = f"mfa_pending:{user.id}"
        await redis_client.setex(key, 600, secret)  # 10 min to complete setup

        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=await self._get_platform_app_name())
        return {"secret": secret, "provisioning_uri": uri}

    async def mfa_verify_enable(self, user: User, code: str) -> None:
        try:
            import pyotp
        except ImportError:
            raise HTTPException(status_code=501, detail="MFA not available")

        key = f"mfa_pending:{user.id}"
        secret = await redis_client.get(key)
        if not secret:
            raise HTTPException(status_code=400, detail="MFA setup session expired. Start again.")

        if not pyotp.TOTP(secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")

        user.mfa_secret = secret
        user.mfa_enabled = True
        await self.db.commit()
        await redis_client.delete(key)

    async def mfa_disable(self, user: User, code: str) -> None:
        try:
            import pyotp
        except ImportError:
            raise HTTPException(status_code=501, detail="MFA not available")

        if not user.mfa_enabled or not user.mfa_secret:
            raise HTTPException(status_code=400, detail="MFA is not enabled")

        if not pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")

        user.mfa_enabled = False
        user.mfa_secret = None
        await self.db.commit()
