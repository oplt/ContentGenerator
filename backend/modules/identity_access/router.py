from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.core.rate_limit import auth_rate_limit_key, check_rate_limit
from backend.modules.identity_access.models import User
from backend.modules.identity_access.schemas import (
    AuthTokensResponse,
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

_REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


def _build_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        mfa_enabled=user.mfa_enabled,
    )


# ------------------------------------------------------------------ core auth

@router.post("/sign-up", response_model=AuthUserResponse, status_code=201)
async def sign_up(payload: SignUpRequest, db: AsyncSession = Depends(get_db)):
    service = IdentityService(db)
    user = await service.sign_up(
        payload.email,
        payload.password,
        payload.full_name,
        payload.admin_invite_code,
    )
    return _build_user(user)


@router.post("/sign-in", response_model=AuthTokensResponse)
async def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=auth_rate_limit_key(request, payload.email),
        max_attempts=10,
        window_seconds=60,
    )
    service = IdentityService(db)
    result = await service.sign_in(payload.email, payload.password)
    _set_refresh_cookie(response, result["refresh_token"])
    return AuthTokensResponse(access_token=result["access_token"], user=_build_user(result["user"]))


@router.post("/refresh", response_model=AuthTokensResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing refresh token")
    service = IdentityService(db)
    result = await service.refresh(refresh_token)
    _set_refresh_cookie(response, result["refresh_token"])
    return AuthTokensResponse(access_token=result["access_token"], user=_build_user(result["user"]))


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    if refresh_token:
        service = IdentityService(db)
        await service.logout(refresh_token)
    response.delete_cookie("refresh_token", path="/api/v1/auth")


@router.get("/me", response_model=AuthUserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return _build_user(current_user)


# ------------------------------------------------------------------ email verification

@router.post("/verify-email", status_code=204)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    service = IdentityService(db)
    await service.verify_email(payload.token)


@router.post("/resend-verification", status_code=204)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=f"rate_limit:resend:{request.client.host if request.client else 'unknown'}",
        max_attempts=3,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.resend_verification(payload.email)


# ------------------------------------------------------------------ password reset

@router.post("/forgot-password", status_code=204)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=f"rate_limit:forgot:{request.client.host if request.client else 'unknown'}:{payload.email}",
        max_attempts=5,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.forgot_password(payload.email)


@router.post("/reset-password", status_code=204)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    service = IdentityService(db)
    await service.reset_password(payload.token, payload.new_password)


# ------------------------------------------------------------------ MFA

@router.post("/mfa/enable", response_model=MfaEnableResponse)
async def mfa_enable(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IdentityService(db)
    return await service.mfa_enable(current_user)


@router.post("/mfa/verify", status_code=204)
async def mfa_verify(
    payload: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IdentityService(db)
    await service.mfa_verify_enable(current_user, payload.code)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    payload: MfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = IdentityService(db)
    await service.mfa_disable(current_user, payload.code)
