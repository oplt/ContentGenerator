from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.security import generate_csrf_token
from backend.core.rate_limit import (
    auth_rate_limit_key,
    check_rate_limit,
    clear_auth_failures,
    enforce_auth_lock,
    record_auth_failure,
)
from backend.modules.identity_access.models import User
from backend.modules.identity_access.auth_cookies import (
    PERSIST_COOKIE as _PERSIST_COOKIE,
    assert_csrf as _assert_csrf,
    set_auth_cookies as _set_auth_cookies,
)
from backend.modules.identity_access.schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    MfaDisableRequest,
    MfaEnableResponse,
    MfaVerifyRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignUpRequest,
    VerifyEmailRequest,
)
from backend.modules.identity_access.service import IdentityService

router = APIRouter()


def _session_user(result: dict[str, object]) -> User:
    user = result.get("user")
    if not isinstance(user, User):
        raise HTTPException(status_code=500, detail="Invalid authentication session")
    return user

@router.post("/sign-up", response_model=AuthSessionResponse, status_code=202)
async def sign_up(
    payload: SignUpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    await check_rate_limit(
        key=f"rate_limit:signup:{request.client.host if request.client else 'unknown'}:{payload.email.lower()}",
        max_attempts=5,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.sign_up(
        payload.email,
        payload.password,
        payload.full_name,
        payload.admin_invite_code,
    )
    return AuthSessionResponse(
        requires_email_verification=True,
        message="If the account can be registered, a verification email will be sent.",
    )


@router.post("/sign-in", response_model=AuthSessionResponse)
async def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    rate_limit_key = auth_rate_limit_key(request, payload.email)
    await enforce_auth_lock(rate_limit_key)
    await check_rate_limit(
        key=rate_limit_key,
        max_attempts=10,
        window_seconds=60,
    )
    service = IdentityService(db)
    try:
        result = await service.sign_in(payload.email, payload.password, payload.mfa_code)
    except HTTPException:
        await record_auth_failure(rate_limit_key)
        raise
    await clear_auth_failures(rate_limit_key)
    csrf = generate_csrf_token()
    _set_auth_cookies(
        response,
        str(result["access_token"]),
        str(result["refresh_token"]),
        csrf,
        remember_me=payload.remember_me,
    )
    return AuthSessionResponse(
        user=await service.build_auth_user(_session_user(result)),
        csrf_token=csrf,
    )


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    csrf_token: str | None = Cookie(default=None),
    sf_persist: str | None = Cookie(default=None, alias=_PERSIST_COOKIE),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: AsyncSession = Depends(get_db),
) -> AuthSessionResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    _assert_csrf(csrf_token, x_csrf_token)
    service = IdentityService(db)
    result = await service.refresh(refresh_token)
    csrf = generate_csrf_token()
    _set_auth_cookies(
        response,
        str(result["access_token"]),
        str(result["refresh_token"]),
        csrf,
        # Missing cookie = legacy persistent sessions (pre-remember_me flag).
        remember_me=sf_persist != "0",
    )
    return AuthSessionResponse(
        user=await service.build_auth_user(_session_user(result)),
        csrf_token=csrf,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    csrf_token: str | None = Cookie(default=None),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: AsyncSession = Depends(get_db),
) -> None:
    _assert_csrf(csrf_token, x_csrf_token)
    if refresh_token:
        service = IdentityService(db)
        await service.logout(refresh_token)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
    response.delete_cookie("csrf_token", path="/")
    response.delete_cookie(_PERSIST_COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=AuthUserResponse)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthUserResponse:
    service = IdentityService(db)
    return await service.build_auth_user(current_user)


@router.post("/verify-email", status_code=204)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    await check_rate_limit(
        key=f"rate_limit:verify:{request.client.host if request.client else 'unknown'}",
        max_attempts=10,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.verify_email(payload.token)


@router.post("/resend-verification", status_code=204)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    await check_rate_limit(
        key=f"rate_limit:resend:{request.client.host if request.client else 'unknown'}",
        max_attempts=3,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.resend_verification(payload.email)


@router.post("/forgot-password", status_code=204)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    await check_rate_limit(
        key=f"rate_limit:forgot:{request.client.host if request.client else 'unknown'}:{payload.email}",
        max_attempts=5,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.forgot_password(payload.email)


@router.post("/reset-password", status_code=204)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    await check_rate_limit(
        key=f"rate_limit:reset:{request.client.host if request.client else 'unknown'}",
        max_attempts=5,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.reset_password(payload.token, payload.new_password)


@router.post("/mfa/enable", response_model=MfaEnableResponse)
async def mfa_enable(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MfaEnableResponse:
    service = IdentityService(db)
    result = await service.mfa_enable(current_user)
    return MfaEnableResponse(**result)


@router.post("/mfa/verify", status_code=204)
async def mfa_verify(
    payload: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    service = IdentityService(db)
    await service.mfa_verify_enable(current_user, payload.code)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    payload: MfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    service = IdentityService(db)
    await service.mfa_disable(current_user, payload.code)
