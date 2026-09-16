"""Authentication cookie and CSRF helpers."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import HTTPException, Response

from backend.core.config import settings
from backend.core.security import verify_csrf_token

REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS
ACCESS_COOKIE_MAX_AGE = 60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES
COOKIE_SAMESITE = cast(Literal["lax", "strict", "none"], settings.cookie_samesite)
PERSIST_COOKIE = "sf_persist"


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    *,
    remember_me: bool = True,
) -> None:
    access_max_age = ACCESS_COOKIE_MAX_AGE if remember_me else None
    refresh_max_age = REFRESH_COOKIE_MAX_AGE if remember_me else None
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=access_max_age,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=refresh_max_age,
        path="/api/v1/auth",
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=refresh_max_age,
        path="/",
    )
    response.set_cookie(
        key=PERSIST_COOKIE,
        value="1" if remember_me else "0",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=refresh_max_age if remember_me else None,
        path="/api/v1/auth",
    )


def assert_csrf(csrf_cookie: str | None, csrf_header: str | None) -> None:
    if not verify_csrf_token(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF verification failed")
