"""Sign-in, refresh, and logout session flows."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.security import (
    create_access_token,
    decrypt_secret,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from backend.core.time_utils import as_utc, utc_now
from backend.modules.identity_access.system_roles import hash_token


class AuthSessionsMixin:
    """Password sign-in and refresh-token session lifecycle."""

    repo: Any
    db: Any
    audit: Any

    async def sign_in(self, email: str, password: str, mfa_code: str | None = None) -> dict[str, object]:
        user = await self.repo.get_user_by_email(email.lower())
        if not user or not verify_password(password, user.password_hash):
            await self.audit.record(
                tenant_id=None,
                actor_user_id=None,
                action="identity.sign_in_failed",
                entity_type="user",
                entity_id=None,
                message="Invalid sign-in credentials",
                payload={"email_hash": hash_token(email.lower())},
            )
            await self.db.commit()
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.is_active:
            await self.audit.record(
                tenant_id=user.default_tenant_id,
                actor_user_id=user.id,
                action="identity.sign_in_failed",
                entity_type="user",
                entity_id=str(user.id),
                message="Disabled account sign-in attempted",
            )
            await self.db.commit()
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if settings.MFA_ACCESS and user.is_admin and user.mfa_enabled:
            import pyotp

            if not mfa_code or not user.mfa_secret:
                await self.audit.record(
                    tenant_id=user.default_tenant_id,
                    actor_user_id=user.id,
                    action="identity.sign_in_failed",
                    entity_type="user",
                    entity_id=str(user.id),
                    message="Admin MFA code missing during sign-in",
                )
                await self.db.commit()
                raise HTTPException(status_code=401, detail="Invalid email or password")
            raw_secret = decrypt_secret(user.mfa_secret)
            if not pyotp.TOTP(raw_secret).verify(mfa_code, valid_window=1):
                await self.audit.record(
                    tenant_id=user.default_tenant_id,
                    actor_user_id=user.id,
                    action="identity.sign_in_failed",
                    entity_type="user",
                    entity_id=str(user.id),
                    message="Admin MFA code invalid during sign-in",
                )
                await self.db.commit()
                raise HTTPException(status_code=401, detail="Invalid email or password")

        raw_refresh = generate_refresh_token()
        expires_at = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session = await self.repo.create_refresh_session(
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
            "access_token": create_access_token(str(user.id), str(session.id)),
            "refresh_token": raw_refresh,
            "user": user,
        }

    async def refresh(self, raw_refresh_token: str) -> dict[str, object]:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)
        if not session or session.is_revoked:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        session_expires_at = as_utc(session.expires_at)
        if session_expires_at is None or session_expires_at < utc_now():
            raise HTTPException(status_code=401, detail="Refresh token expired")

        user = await self.repo.get_user_by_id(session.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or disabled")

        await self.repo.revoke_refresh_session(session)
        new_raw = generate_refresh_token()
        new_expires = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        new_session = await self.repo.create_refresh_session(
            user_id=user.id,
            token_hash=hash_refresh_token(new_raw),
            expires_at=new_expires,
        )
        await self.db.commit()
        return {
            "access_token": create_access_token(str(user.id), str(new_session.id)),
            "refresh_token": new_raw,
            "user": user,
        }

    async def logout(self, raw_refresh_token: str) -> None:
        refresh_hash = hash_refresh_token(raw_refresh_token)
        session = await self.repo.get_refresh_session_by_hash(refresh_hash)
        if session:
            await self.repo.revoke_refresh_session(session)
            await self.db.commit()
