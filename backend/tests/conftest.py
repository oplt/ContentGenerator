from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.db import model_registry  # noqa: F401
from backend.db.base import Base
from backend.modules.identity_access.models import MembershipStatus, Role, Tenant, TenantUser, User


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def seeded_context(db_session: AsyncSession) -> dict[str, object]:
    tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
    user = User(email="demo@example.com", password_hash="hashed")
    role = Role(name="Owner", slug="owner", description="Owner", is_system=True, permission_codes=["content:write", "publishing:write", "analytics:read", "sources:write", "settings:write"])
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
    return {"tenant": tenant, "user": user, "role": role, "membership": membership}
