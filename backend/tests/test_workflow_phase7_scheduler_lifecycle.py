"""Phase 7 — harden scheduler lifecycle (next_run_at sync, DST, occurrences)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any, cast
from zoneinfo import ZoneInfo

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
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workflows.occurrence_sync import sync_occurrence_for_run
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun, WorkflowRunStatus
from backend.modules.workflows.schedule_next import (
    combine_local_wall_time,
    compute_next_run_at,
)
from backend.modules.workflows.scheduler import AutomationScheduler


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


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
                        TaskExecution.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                        AutomationOccurrence.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


async def _seed_automation(
    db: AsyncSession,
    *,
    enabled: bool = True,
    trigger_type: str = AutomationTriggerType.SCHEDULE.value,
    trigger_config: dict[str, Any] | None = None,
    timezone_name: str = "Europe/Brussels",
    next_run_at: datetime | None = None,
) -> Automation:
    tenant = Tenant(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    brand = Brand(tenant_id=tenant.id, name="b", niche="n")
    db.add(brand)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="wf",
        slug=f"wf-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json={"nodes": [], "edges": []},
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
        name="sched",
        enabled=enabled,
        trigger_type=trigger_type,
        trigger_config=trigger_config or {"kind": "daily", "at": "09:00"},
        timezone=timezone_name,
        next_run_at=next_run_at,
    )
    db.add(automation)
    await db.flush()
    return automation


def test_brussels_spring_dst_nonexistent_local_time() -> None:
    """2026-03-29 Europe/Brussels: 02:00→03:00. 02:30 does not exist → first valid after gap."""
    tz = ZoneInfo("Europe/Brussels")
    resolved = combine_local_wall_time(tz, date(2026, 3, 29), 2, 30)
    local = resolved.astimezone(tz)
    assert local.hour == 3 and local.minute == 0
    assert local.date() == date(2026, 3, 29)

    after = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
    nxt = compute_next_run_at(
        trigger_config={"kind": "daily", "at": "02:30"},
        timezone_name="Europe/Brussels",
        after=after,
    )
    local_nxt = nxt.astimezone(tz)
    assert local_nxt.date() == date(2026, 3, 29)
    assert (local_nxt.hour, local_nxt.minute) == (3, 0)


def test_brussels_autumn_dst_ambiguous_local_time() -> None:
    """2026-10-25 Europe/Brussels: 03:00→02:00. Prefer fold=0 (earlier occurrence)."""
    tz = ZoneInfo("Europe/Brussels")
    resolved = combine_local_wall_time(tz, date(2026, 10, 25), 2, 30)
    assert resolved.fold == 0
    earlier = datetime(2026, 10, 25, 2, 30, tzinfo=tz, fold=0)
    later = datetime(2026, 10, 25, 2, 30, tzinfo=tz, fold=1)
    assert earlier.astimezone(timezone.utc) != later.astimezone(timezone.utc)
    assert resolved.astimezone(timezone.utc) == earlier.astimezone(timezone.utc)

    after = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
    nxt = compute_next_run_at(
        trigger_config={"kind": "daily", "at": "02:30"},
        timezone_name="Europe/Brussels",
        after=after,
    )
    assert nxt == earlier.astimezone(timezone.utc)


def test_brussels_weekly_and_cron_across_dst() -> None:
    tz = ZoneInfo("Europe/Brussels")
    # Weekly Mon 02:30 after Sat before spring DST Sunday.
    after = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)  # Saturday
    weekly = compute_next_run_at(
        trigger_config={"kind": "weekly", "days": ["mon"], "at": "02:30"},
        timezone_name="Europe/Brussels",
        after=after,
    )
    local = weekly.astimezone(tz)
    assert local.weekday() == 0  # Monday 2026-03-30 (after DST)
    assert (local.hour, local.minute) == (2, 30)

    cron = compute_next_run_at(
        trigger_config={"kind": "cron", "expr": "30 2 * * *"},
        timezone_name="Europe/Brussels",
        after=datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc),
    )
    cron_local = cron.astimezone(tz)
    # Nonexistent 02:30 on Mar 29 → first valid (03:00) via combine_local.
    assert cron_local.date() == date(2026, 3, 29)
    assert (cron_local.hour, cron_local.minute) == (3, 0)


def test_sync_schedule_state_rules() -> None:
    async def _run() -> None:
        db = await _async_session()
        scheduler = AutomationScheduler(db)
        now = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)

        disabled = await _seed_automation(
            db,
            enabled=False,
            next_run_at=now - timedelta(hours=1),
        )
        await scheduler.sync_schedule_state(disabled, now=now, force_recompute=True)
        assert disabled.next_run_at is None

        manual = await _seed_automation(
            db,
            enabled=True,
            trigger_type=AutomationTriggerType.MANUAL.value,
            next_run_at=now + timedelta(hours=1),
        )
        await scheduler.sync_schedule_state(manual, now=now, force_recompute=True)
        assert manual.next_run_at is None

        enabled = await _seed_automation(
            db,
            enabled=True,
            trigger_config={"kind": "interval", "every_seconds": 3600},
            timezone_name="UTC",
            next_run_at=None,
        )
        await scheduler.sync_schedule_state(enabled, now=now, force_recompute=True)
        assert enabled.next_run_at is not None
        assert enabled.next_run_at.replace(tzinfo=timezone.utc) == now + timedelta(hours=1)

        # Config / tz change: recompute from now, not preserve stale slot.
        enabled.trigger_config = {"kind": "interval", "every_seconds": 7200}
        stale = now - timedelta(days=2)
        enabled.next_run_at = stale
        await scheduler.sync_schedule_state(enabled, now=now, force_recompute=True)
        assert enabled.next_run_at is not None
        assert enabled.next_run_at.replace(tzinfo=timezone.utc) == now + timedelta(hours=2)
        assert enabled.next_run_at.replace(tzinfo=timezone.utc) != stale

        # Re-enable after disable: never fire obsolete past slot.
        enabled.enabled = False
        await scheduler.sync_schedule_state(enabled, now=now, force_recompute=True)
        assert enabled.next_run_at is None
        enabled.enabled = True
        enabled.next_run_at = now - timedelta(hours=5)  # obsolete leftover
        await scheduler.sync_schedule_state(enabled, now=now, force_recompute=True)
        assert enabled.next_run_at is not None
        nxt = enabled.next_run_at
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        assert nxt > now

        await db.close()

    asyncio.run(_run())


def test_occurrence_sync_from_terminal_run() -> None:
    async def _run() -> None:
        db = await _async_session()
        automation = await _seed_automation(db)
        run = WorkflowRun(
            tenant_id=automation.tenant_id,
            workflow_definition_id=automation.workflow_definition_id,
            workflow_version_id=automation.workflow_version_id,
            automation_id=automation.id,
            status=WorkflowRunStatus.RUNNING.value,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            context_snapshot={},
            trigger_payload={},
        )
        db.add(run)
        await db.flush()
        occ = AutomationOccurrence(
            tenant_id=automation.tenant_id,
            automation_id=automation.id,
            scheduled_for=datetime.now(timezone.utc),
            scheduled_occurrence="2026-09-16T08:00:00Z",
            status=AutomationOccurrenceStatus.STARTED.value,
            workflow_run_id=run.id,
        )
        db.add(occ)
        await db.flush()

        run.status = WorkflowRunStatus.SUCCEEDED.value
        await sync_occurrence_for_run(db, run)
        await db.flush()
        assert occ.status == AutomationOccurrenceStatus.SUCCEEDED.value

        # Idempotent once terminal.
        run.status = WorkflowRunStatus.FAILED.value
        await sync_occurrence_for_run(db, run)
        assert occ.status == AutomationOccurrenceStatus.SUCCEEDED.value

        # Failed path
        run2 = WorkflowRun(
            tenant_id=automation.tenant_id,
            workflow_definition_id=automation.workflow_definition_id,
            workflow_version_id=automation.workflow_version_id,
            automation_id=automation.id,
            status=WorkflowRunStatus.FAILED.value,
            error_message="boom",
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            context_snapshot={},
            trigger_payload={},
        )
        db.add(run2)
        await db.flush()
        occ2 = AutomationOccurrence(
            tenant_id=automation.tenant_id,
            automation_id=automation.id,
            scheduled_for=datetime.now(timezone.utc),
            scheduled_occurrence="2026-09-16T09:00:00Z",
            status=AutomationOccurrenceStatus.STARTED.value,
            workflow_run_id=run2.id,
        )
        db.add(occ2)
        await db.flush()
        await sync_occurrence_for_run(db, run2)
        assert occ2.status == AutomationOccurrenceStatus.FAILED.value
        assert occ2.error_message == "boom"

        run3 = WorkflowRun(
            tenant_id=automation.tenant_id,
            workflow_definition_id=automation.workflow_definition_id,
            workflow_version_id=automation.workflow_version_id,
            automation_id=automation.id,
            status=WorkflowRunStatus.CANCELLED.value,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            context_snapshot={},
            trigger_payload={},
        )
        db.add(run3)
        await db.flush()
        occ3 = AutomationOccurrence(
            tenant_id=automation.tenant_id,
            automation_id=automation.id,
            scheduled_for=datetime.now(timezone.utc),
            scheduled_occurrence="2026-09-16T10:00:00Z",
            status=AutomationOccurrenceStatus.STARTED.value,
            workflow_run_id=run3.id,
        )
        db.add(occ3)
        await db.flush()
        await sync_occurrence_for_run(db, run3)
        assert occ3.status == AutomationOccurrenceStatus.SKIPPED.value
        await db.close()

    asyncio.run(_run())
