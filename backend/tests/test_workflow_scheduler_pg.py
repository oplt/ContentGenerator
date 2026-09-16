"""Postgres-backed concurrent claim tests for automation scheduler (Phase 4)."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import settings
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.workflows.models import (
    Automation,
    AutomationTriggerType,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workflows.scheduler import AutomationScheduler


def _postgres_url() -> str | None:
    url = settings.DATABASE_URL
    if "postgresql" not in url and "postgres" not in url:
        return None
    return url


@pytest.mark.integration
def test_postgres_concurrent_claim_due_skip_locked() -> None:
    """Two connections: only one claims a due automation while the other holds the lock."""
    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1" and os.environ.get("CG_RUN_PG_SCHEDULER") != "1":
        pytest.skip("set CG_RUN_PG_SCHEDULER=1 (or CG_RUN_DB_MIGRATIONS=1) for live Postgres")

    url = _postgres_url()
    if url is None:
        pytest.skip("DATABASE_URL is not Postgres")

    async def _run() -> None:
        engine = create_async_engine(url, pool_size=2, max_overflow=0)
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        setup = Session()
        tenant = Tenant(name="SchedRace", slug=f"sched-race-{uuid.uuid4().hex[:8]}")
        setup.add(tenant)
        await setup.flush()
        brand = Brand(tenant_id=tenant.id, name="Race", niche="test")
        setup.add(brand)
        await setup.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id,
            name="Race WF",
            slug=f"race-{uuid.uuid4().hex[:8]}",
            status="active",
        )
        setup.add(definition)
        await setup.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json={
                "nodes": [{"id": "t", "type": "manual_trigger", "version": 1, "config": {}}],
                "edges": [],
            },
            published_at=datetime.now(timezone.utc),
            checksum="race",
        )
        setup.add(version)
        await setup.flush()
        definition.current_version_id = version.id
        due = datetime.now(timezone.utc) - timedelta(minutes=1)
        automation = Automation(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            workflow_version_id=version.id,
            brand_id=brand.id,
            name="Race Auto",
            enabled=True,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            trigger_config={"kind": "interval", "every_seconds": 3600},
            timezone="UTC",
            next_run_at=due,
            settings={},
        )
        setup.add(automation)
        await setup.commit()
        auto_id = automation.id
        await setup.close()

        gate = asyncio.Event()
        claimed: list[list[uuid.UUID]] = []

        async def worker(hold: bool) -> None:
            db = Session()
            try:
                async with db.begin():
                    rows = await AutomationScheduler(db).repo.claim_due_automations(
                        now=datetime.now(timezone.utc), limit=10
                    )
                    ids = [row.id for row in rows if row.id == auto_id]
                    claimed.append(ids)
                    if hold:
                        gate.set()
                        await asyncio.sleep(0.4)
            finally:
                await db.close()

        async def second() -> None:
            await gate.wait()
            await worker(hold=False)

        await asyncio.gather(worker(hold=True), second())
        assert sum(1 for batch in claimed if auto_id in batch) == 1

        cleanup = Session()
        auto = await cleanup.get(Automation, auto_id)
        if auto is not None:
            await cleanup.delete(auto)
        await cleanup.commit()
        await cleanup.close()
        await engine.dispose()

    asyncio.run(_run())
