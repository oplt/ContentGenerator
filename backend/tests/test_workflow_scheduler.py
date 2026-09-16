"""Phase 7 — DB-backed automation scheduler."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand, BrandProfile
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.models import (
    Automation,
    AutomationOccurrence,
    AutomationOccurrenceStatus,
    AutomationTarget,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.schedule_next import compute_next_run_at, occurrence_key
from backend.modules.workflows.scheduler import AutomationScheduler


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _trigger_generate_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 64},
            },
        ],
        "edges": [{"source": "trigger", "target": "generate"}],
    }


async def _async_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
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
                        BrandProfile.__table__,
                        SocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        AutomationTarget.__table__,
                        TaskExecution.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                        AutomationOccurrence.__table__,
                    ],
                ),
            )
        )

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return Session()


async def _seed_schedule_automation(
    db: AsyncSession,
    *,
    next_run_at: datetime,
    trigger_config: dict[str, Any] | None = None,
) -> tuple[Tenant, Automation]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    brand = Brand(tenant_id=tenant.id, name="Chess", niche="chess")
    db.add(brand)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Sched",
        slug=f"sched-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json=_trigger_generate_graph(),
        published_at=datetime.now(timezone.utc),
        checksum="test",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    automation = Automation(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        workflow_version_id=version.id,
        brand_id=brand.id,
        name="Daily Chess",
        enabled=True,
        trigger_type=AutomationTriggerType.SCHEDULE.value,
        trigger_config=trigger_config
        or {"kind": "interval", "every_seconds": 3600},
        timezone="UTC",
        next_run_at=next_run_at,
        settings={"trigger_payload": {"prompt": "scheduled hello"}},
    )
    db.add(automation)
    await db.flush()
    return tenant, automation


def test_compute_next_interval_daily_weekly_cron() -> None:
    after = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)
    nxt = compute_next_run_at(
        trigger_config={"kind": "interval", "every_seconds": 3600},
        timezone_name="UTC",
        after=after,
    )
    assert nxt == after + timedelta(hours=1)

    daily = compute_next_run_at(
        trigger_config={"kind": "daily", "at": "09:00"},
        timezone_name="Europe/Brussels",
        after=after,
    )
    assert daily > after
    local = daily.astimezone(__import__("zoneinfo").ZoneInfo("Europe/Brussels"))
    assert local.hour == 9 and local.minute == 0

    weekly = compute_next_run_at(
        trigger_config={"kind": "weekly", "days": ["mon"], "at": "09:00"},
        timezone_name="UTC",
        after=after,  # Wednesday
    )
    assert weekly.weekday() == 0

    cron = compute_next_run_at(
        trigger_config={"kind": "cron", "expr": "0 9 * * *"},
        timezone_name="UTC",
        after=after,
    )
    assert cron == datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)


def test_tick_creates_occurrence_and_run() -> None:
    async def _run() -> None:
        db = await _async_session()
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        _tenant, automation = await _seed_schedule_automation(db, next_run_at=due)
        scheduler = AutomationScheduler(db)
        results = await scheduler.tick(now=datetime.now(timezone.utc), enqueue_advance=False)
        assert len(results) == 1
        assert results[0].status == "started"
        assert results[0].workflow_run_id is not None
        assert automation.next_run_at is not None
        assert automation.next_run_at > due
        assert automation.last_run_at is not None

        occ = await scheduler.repo.get_occurrence(
            automation.id, results[0].scheduled_occurrence
        )
        assert occ is not None
        assert occ.status == AutomationOccurrenceStatus.STARTED.value
        assert occ.workflow_run_id == results[0].workflow_run_id

        run = await scheduler.engine.runs.get_run(_tenant.id, results[0].workflow_run_id)
        assert run is not None
        assert run.trigger_type == AutomationTriggerType.SCHEDULE.value
        assert run.status == WorkflowRunStatus.RUNNING.value
        assert run.correlation_id == f"sched:{automation.id}:{results[0].scheduled_occurrence}"
        await db.close()

    asyncio.run(_run())


def test_tick_idempotent_same_occurrence() -> None:
    async def _run() -> None:
        db = await _async_session()
        due = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
        _tenant, automation = await _seed_schedule_automation(
            db,
            next_run_at=due,
            trigger_config={"kind": "interval", "every_seconds": 86_400},
        )
        scheduler = AutomationScheduler(db)
        # Force next_run back to same slot after first fire to simulate retry race.
        first = await scheduler.tick(now=due + timedelta(seconds=1), enqueue_advance=False)
        assert first[0].status == "started"
        key = occurrence_key(due)
        automation.next_run_at = due
        await db.flush()
        second = await scheduler.tick(now=due + timedelta(seconds=2), enqueue_advance=False)
        assert second[0].status == "skipped"
        assert second[0].scheduled_occurrence == key
        await db.close()

    asyncio.run(_run())


def test_tick_enqueues_advance_task() -> None:
    async def _run() -> None:
        db = await _async_session()
        due = datetime.now(timezone.utc) - timedelta(seconds=30)
        await _seed_schedule_automation(db, next_run_at=due)
        scheduler = AutomationScheduler(db)
        with patch(
            "backend.workers.tasks.advance_workflow_run_task"
        ) as advance_task:
            advance_task.delay = lambda **kwargs: None
            # Patch via scheduler module path used by _enqueue_advance
            with patch(
                "backend.modules.workflows.scheduler.AutomationScheduler._enqueue_advance"
            ) as enqueue:
                results = await scheduler.tick(
                    now=datetime.now(timezone.utc), enqueue_advance=True
                )
                assert results[0].status == "started"
                enqueue.assert_called_once()
        await db.close()

    asyncio.run(_run())
