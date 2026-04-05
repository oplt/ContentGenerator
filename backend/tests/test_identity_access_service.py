from __future__ import annotations

from datetime import timedelta

import pytest

from backend.core.security import hash_password
from backend.core.time_utils import utc_now_naive
from backend.modules.identity_access.models import MembershipStatus, Role, Tenant, TenantUser, User
from backend.modules.identity_access.service import IdentityService


@pytest.mark.asyncio
async def test_sign_in_creates_refresh_session(db_session):
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
    user = User(email="demo@example.com", password_hash=hash_password("password1234"))
    role = Role(
        name="Owner",
        slug="owner",
        description="Owner",
        is_system=True,
        permission_codes=["content:write"],
    )
    db_session.add_all([tenant, user, role])
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

    service = IdentityService(db_session)

    result = await service.sign_in("demo@example.com", "password1234")
    sessions = await service.repo.list_active_sessions(user.id)

    assert result["user"].id == user.id
    assert isinstance(result["access_token"], str)
    assert isinstance(result["refresh_token"], str)
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_refresh_accepts_naive_session_expiry(db_session):
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
    user = User(email="demo@example.com", password_hash=hash_password("password1234"))
    role = Role(
        name="Owner",
        slug="owner",
        description="Owner",
        is_system=True,
        permission_codes=["content:write"],
    )
    db_session.add_all([tenant, user, role])
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

    service = IdentityService(db_session)
    sign_in_result = await service.sign_in("demo@example.com", "password1234")

    refreshed = await service.refresh(sign_in_result["refresh_token"])
    sessions = await service.repo.list_active_sessions(user.id)

    assert isinstance(refreshed["access_token"], str)
    assert isinstance(refreshed["refresh_token"], str)
    assert len(sessions) == 1
    assert sessions[0].expires_at > utc_now_naive() + timedelta(days=13)
