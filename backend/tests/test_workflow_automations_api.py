"""Phase 13 — automation HTTP service smoke."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import cast

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.audit.models import AuditLog
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.automation_schemas import AutomationCreateRequest
from backend.modules.workflows.automation_service import AutomationService
from backend.modules.workflows.models import (
    Automation,
    AutomationTarget,
    WorkflowDefinition,
    WorkflowVersion,
)


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [
                        Tenant.__table__,
                        Brand.__table__,
                        SocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        AutomationTarget.__table__,
                        AuditLog.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


def test_create_automation_with_targets() -> None:
    async def _run() -> None:
        db = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        brand = Brand(tenant_id=tenant.id, name="Chess", niche="chess")
        db.add(brand)
        await db.flush()
        account = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="ChessX",
            handle="@chess",
            auth_type="stub",
            capability_flags={"text": "true"},
            settings={},
        )
        db.add(account)
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Daily", slug="daily", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            published_at=datetime.now(timezone.utc),
            checksum="c",
        )
        db.add(version)
        await db.flush()
        definition.current_version_id = version.id
        await db.commit()

        svc = AutomationService(db)
        created = await svc.create_automation(
            tenant.id,
            AutomationCreateRequest(
                name="Morning",
                workflow_definition_id=definition.id,
                brand_id=brand.id,
                social_account_ids=[account.id],
                enabled=False,
            ),
        )
        assert created.name == "Morning"
        assert len(created.targets) == 1
        listed = await svc.list_automations(tenant.id)
        assert len(listed) == 1
        await db.close()

    asyncio.run(_run())
