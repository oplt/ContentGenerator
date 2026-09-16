"""Successful auth sign-in HTTP contract (bugs.txt P0)."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI

from backend.api.deps.db import get_db
from backend.core.error_handler import register_exception_handlers
from backend.modules.identity_access import router as auth_router
from backend.modules.identity_access.models import User
from backend.modules.identity_access.schemas import (
    AuthUserResponse,
    SignInRequest,
)


def test_sign_in_request_accepts_empty_mfa_code() -> None:
    """Empty MFA from the form must not 422 (normalized to None)."""
    payload = SignInRequest(
        email="demo@example.com",
        password="password1234",
        mfa_code="",
        remember_me=True,
    )
    assert payload.mfa_code is None


def test_sign_in_http_success_sets_session_cookies(monkeypatch) -> None:
    user = User(
        id=uuid.uuid4(),
        email="demo@example.com",
        full_name="Demo Operator",
        password_hash="x",
        is_active=True,
        is_verified=True,
        is_admin=False,
        mfa_enabled=False,
        default_tenant_id=uuid.uuid4(),
    )
    auth_user = AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_verified=True,
        is_admin=False,
        mfa_enabled=False,
        default_tenant_id=user.default_tenant_id,
        memberships=[],
        rbac_mode="role_based_placeholder",
    )

    class FakeIdentityService:
        def __init__(self, db) -> None:  # noqa: ANN001
            _ = db

        sign_in = AsyncMock(
            return_value={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "user": user,
            }
        )
        build_auth_user = AsyncMock(return_value=auth_user)

    monkeypatch.setattr(auth_router, "IdentityService", FakeIdentityService)
    monkeypatch.setattr(
        auth_router,
        "enforce_auth_lock",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        auth_router,
        "check_rate_limit",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        auth_router,
        "clear_auth_failures",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        auth_router,
        "record_auth_failure",
        AsyncMock(return_value=None),
    )

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth")
    register_exception_handlers(app)

    async def _db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _db

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/auth/sign-in",
                json={
                    "email": "demo@example.com",
                    "password": "password1234",
                    "mfa_code": "",
                    "remember_me": True,
                },
            )

    response = asyncio.run(_request())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "demo@example.com"
    assert body["csrf_token"]
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies
    FakeIdentityService.sign_in.assert_awaited_once()
