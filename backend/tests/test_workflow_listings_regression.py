"""Phase 16 — workflow list endpoints + soft-delete filters (sqlite smoke)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.publishing.models import SocialAccount, SocialAccountStatus
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.workflows.automation_service import AutomationService
from backend.modules.workflows.models import (
    Automation,
    AutomationTarget,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowVersion,
)
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.run_models import WorkflowRun, WorkflowRunStatus
from backend.modules.workflows.run_repository import WorkflowRunRepository


async def _session() -> tuple[AsyncSession, Any]:
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
                        WorkflowRun.__table__,
                    ],
                ),
            )
        )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session(), engine


def test_list_workflow_definitions_succeeds() -> None:
    async def _run() -> None:
        db, engine = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        repo = WorkflowRepository(db)
        definition = WorkflowDefinition(
            tenant_id=tenant.id,
            name="Daily",
            slug=f"daily-{uuid.uuid4().hex[:6]}",
            status=WorkflowDefinitionStatus.ACTIVE.value,
        )
        db.add(definition)
        await db.flush()
        listed = await repo.list_definitions(tenant.id)
        assert len(listed) == 1
        assert listed[0].id == definition.id
        await db.close()
        await engine.dispose()

    asyncio.run(_run())


def test_list_automations_succeeds() -> None:
    async def _run() -> None:
        db, engine = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        brand = Brand(tenant_id=tenant.id, name="Brand", niche="news")
        db.add(brand)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id,
            name="Auto flow",
            slug=f"auto-{uuid.uuid4().hex[:6]}",
            status=WorkflowDefinitionStatus.ACTIVE.value,
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            checksum="phase16",
        )
        db.add(version)
        await db.flush()
        automation = Automation(
            tenant_id=tenant.id,
            brand_id=brand.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            name="Morning",
            enabled=True,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            trigger_config={"kind": "interval", "every_seconds": 3600},
            next_run_at=datetime.now(timezone.utc),
            timezone="UTC",
        )
        db.add(automation)
        await db.flush()
        listed = await AutomationService(db).list_automations(tenant.id)
        assert len(listed) == 1
        assert listed[0].id == automation.id
        await db.close()
        await engine.dispose()

    asyncio.run(_run())


def test_list_workflow_runs_succeeds() -> None:
    async def _run() -> None:
        db, engine = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id,
            name="Run flow",
            slug=f"run-{uuid.uuid4().hex[:6]}",
            status=WorkflowDefinitionStatus.ACTIVE.value,
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={"nodes": [], "edges": []},
            checksum="phase16",
        )
        db.add(version)
        await db.flush()
        run = WorkflowRun(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            status=WorkflowRunStatus.QUEUED.value,
        )
        repo = WorkflowRunRepository(db)
        await repo.add_run(run)
        listed = await repo.list_runs(tenant.id)
        assert [row.id for row in listed] == [run.id]
        await db.close()
        await engine.dispose()

    asyncio.run(_run())


def test_soft_deleted_and_quarantined_social_accounts_excluded_from_list() -> None:
    async def _run() -> None:
        db, engine = await _session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        active = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="Active",
            handle="@active",
            account_external_id="ext-active",
            status=SocialAccountStatus.CONNECTED.value,
        )
        quarantined = SocialAccount(
            tenant_id=tenant.id,
            platform="x",
            display_name="Bad",
            handle="@bad",
            account_external_id="ext-bad",
            status=SocialAccountStatus.QUARANTINED.value,
        )
        deleted = SocialAccount(
            tenant_id=tenant.id,
            platform="bluesky",
            display_name="Gone",
            handle="@gone",
            account_external_id="ext-gone",
            status=SocialAccountStatus.CONNECTED.value,
            deleted_at=datetime.now(timezone.utc),
        )
        db.add_all([active, quarantined, deleted])
        await db.flush()
        listed = await PublishingRepository(db).list_social_accounts(tenant.id)
        assert [row.id for row in listed] == [active.id]
        await db.close()
        await engine.dispose()

    asyncio.run(_run())
