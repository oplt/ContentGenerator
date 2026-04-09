from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.admin import get_admin_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.modules.identity_access.models import MembershipStatus, Role, Tenant, TenantUser, User
from backend.modules.identity_access.router import router as auth_router
from backend.core.security import encrypt_secret, hash_password


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self.redis = redis
        self.ops: list[tuple[str, tuple[object, ...]]] = []

    def incr(self, key: str) -> None:
        self.ops.append(("incr", (key,)))

    def expire(self, key: str, seconds: int) -> None:
        self.ops.append(("expire", (key, seconds)))

    async def execute(self) -> list[int]:
        results: list[int] = []
        for op, args in self.ops:
            if op == "incr":
                results.append(await self.redis.incr(args[0]))
            elif op == "expire":
                await self.redis.expire(args[0], args[1])
                results.append(1)
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self.values[key] = value
        self.ttls[key] = seconds
        return True

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(key in self.values or key in self.ttls)
            self.values.pop(key, None)
            self.ttls.pop(key, None)
        return deleted

    async def incr(self, key: str) -> int:
        current = int(self.values.get(key, "0")) + 1
        self.values[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


@pytest.fixture
async def auth_app(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FastAPI]:
    fake_redis = FakeRedis()
    queued_emails: list[str] = []

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    def fake_queue_email(*, to: str, subject: str, html_body: str, text_body: str) -> None:
        queued_emails.append(to)

    monkeypatch.setattr("backend.modules.identity_access.service.redis_client", fake_redis)
    monkeypatch.setattr("backend.core.rate_limit.redis_client", fake_redis)
    monkeypatch.setattr("backend.modules.identity_access.service.queue_email", fake_queue_email)

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.dependency_overrides[get_db] = override_get_db

    @app.get("/api/v1/protected")
    async def protected(_: User = Depends(get_current_user)) -> dict[str, str]:
        return {"ok": "true"}

    @app.post("/api/v1/protected")
    async def protected_write(_: User = Depends(get_current_user)) -> dict[str, str]:
        return {"ok": "true"}

    yield app


async def _seed_user(db_session: AsyncSession, *, is_admin: bool = False, mfa_enabled: bool = False, mfa_secret: str | None = None, is_verified: bool = True) -> User:
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
    role = Role(
        name="Owner",
        slug="owner",
        description="Owner",
        is_system=True,
        permission_codes=["audit:read", "settings:write"],
    )
    user = User(
        email="demo@example.com",
        password_hash=hash_password("password1234"),
        is_admin=is_admin,
        mfa_enabled=mfa_enabled,
        mfa_secret=mfa_secret,
        is_verified=is_verified,
    )
    db_session.add_all([tenant, role, user])
    await db_session.flush()
    membership = TenantUser(
        tenant_id=tenant.id,
        user_id=user.id,
        role_id=role.id,
        membership_status=MembershipStatus.ACTIVE.value,
    )
    user.default_tenant_id = tenant.id
    db_session.add(membership)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_sign_in_sets_cookie_only_session(auth_app: FastAPI, db_session: AsyncSession):
    await _seed_user(db_session)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "demo@example.com"
        assert "access_token" not in body
        assert client.cookies.get("access_token")
        assert client.cookies.get("refresh_token")
        assert client.cookies.get("csrf_token")


@pytest.mark.asyncio
async def test_admin_sign_in_skips_mfa_when_feature_disabled(
    auth_app: FastAPI,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MFA_ACCESS", False)
    await _seed_user(
        db_session,
        is_admin=True,
        mfa_enabled=True,
        mfa_secret=encrypt_secret("JBSWY3DPEHPK3PXP"),
    )

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )

        assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_sign_in_requires_mfa_when_feature_enabled(
    auth_app: FastAPI,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MFA_ACCESS", True)
    await _seed_user(
        db_session,
        is_admin=True,
        mfa_enabled=True,
        mfa_secret=encrypt_secret("JBSWY3DPEHPK3PXP"),
    )

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_protected_write_requires_csrf(auth_app: FastAPI, db_session: AsyncSession):
    await _seed_user(db_session)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )

        ok = await client.get("/api/v1/protected")
        blocked = await client.post("/api/v1/protected")
        allowed = await client.post(
            "/api/v1/protected",
            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")},
        )

        assert ok.status_code == 200
        assert blocked.status_code == 403
        assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_refresh_rotation_revokes_previous_access_session(auth_app: FastAPI, db_session: AsyncSession):
    await _seed_user(db_session)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )
        original_access = client.cookies.get("access_token")
        original_refresh = client.cookies.get("refresh_token")

        refreshed = await client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": client.cookies.get("csrf_token", "")},
        )
        assert refreshed.status_code == 200
        assert client.cookies.get("refresh_token") != original_refresh
        assert client.cookies.get("access_token") != original_access

        stale_client = AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver")
        stale_client.cookies.set("access_token", original_access or "")
        stale_client.cookies.set("csrf_token", client.cookies.get("csrf_token", ""))
        stale_response = await stale_client.get("/api/v1/protected")
        await stale_client.aclose()

        assert stale_response.status_code == 401


@pytest.mark.asyncio
async def test_sign_in_uses_generic_error_and_locks_after_repeated_failures(auth_app: FastAPI, db_session: AsyncSession):
    await _seed_user(db_session)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        for _ in range(5):
            response = await client.post(
                "/api/v1/auth/sign-in",
                json={"email": "missing@example.com", "password": "wrong-password"},
            )
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid email or password"

        locked = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "missing@example.com", "password": "wrong-password"},
        )
        assert locked.status_code == 429


@pytest.mark.asyncio
async def test_get_admin_user_skips_mfa_requirement_when_feature_disabled(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "MFA_ACCESS", False)
    user = await _seed_user(db_session, is_admin=True, mfa_enabled=False)

    resolved = await get_admin_user(user)

    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_duplicate_sign_up_does_not_reveal_account_existence(auth_app: FastAPI, db_session: AsyncSession):
    await _seed_user(db_session)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-up",
            json={"email": "demo@example.com", "password": "password1234"},
        )

        assert response.status_code == 202
        assert response.json()["requires_email_verification"] is True


@pytest.mark.asyncio
async def test_sign_up_skips_auth_email_when_disabled(
    auth_app: FastAPI,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    queued_emails: list[str] = []

    def fake_queue_email(*, to: str, subject: str, html_body: str, text_body: str) -> None:
        queued_emails.append(to)

    monkeypatch.setattr("backend.modules.identity_access.service.queue_email", fake_queue_email)
    monkeypatch.setattr("backend.modules.identity_access.service.settings.SEND_AUTH_EMAIL_ON_SIGNUP", False)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-up",
            json={"email": "new-user@example.com", "password": "password1234"},
        )

    assert response.status_code == 202
    assert queued_emails == []


@pytest.mark.asyncio
async def test_unverified_user_is_treated_as_verified_when_auth_email_disabled(
    auth_app: FastAPI,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    await _seed_user(db_session, is_verified=False)
    monkeypatch.setattr("backend.modules.identity_access.service.settings.SEND_AUTH_EMAIL_ON_SIGNUP", False)

    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": "demo@example.com", "password": "password1234"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["is_verified"] is True
