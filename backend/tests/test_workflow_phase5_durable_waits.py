"""Phase 5 — durable WorkflowWait (Postgres owns wake_at)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_resume import resume_waiting_node
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
    WorkflowWaitStatus,
    WorkflowWaitType,
)
from backend.modules.workflows.wait_recovery import wake_due_workflow_waits
from backend.modules.workflows.wait_store import claim_due_waits, resolve_wait_by_event_key


@pytest.fixture(autouse=True)
def _fresh_registry():
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
                        TaskExecution.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                        WorkflowWait.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


def _delay_graph(duration: int = 60) -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "delay",
                "type": "delay",
                "version": 1,
                "config": {"duration_seconds": duration},
            },
            {
                "id": "done",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 16},
            },
        ],
        "edges": [
            {"source": "trigger", "target": "delay"},
            {"source": "delay", "target": "done"},
        ],
    }


def test_delay_persists_workflow_wait_row() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="D", slug="d", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_delay_graph(120),
            published_at=datetime.now(timezone.utc),
            checksum="d",
        )
        db.add(version)
        await db.commit()

        with patch("backend.modules.workflows.wait_persist.schedule_fast_wake") as fast:
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"prompt": "hi"},
                compile_context=CompileContext(require_publish_targets=False),
            )
        assert run.status == WorkflowRunStatus.WAITING.value
        assert fast.called
        waits = (
            await db.execute(
                select(WorkflowWait).where(WorkflowWait.workflow_run_id == run.id)
            )
        ).scalars().all()
        assert len(waits) == 1
        wait = waits[0]
        assert wait.wait_type == WorkflowWaitType.DELAY.value
        assert wait.status == WorkflowWaitStatus.PENDING.value
        assert wait.wake_at is not None
        assert wait.resume_token
        await db.close()

    asyncio.run(_run())


def test_wake_due_resolves_and_continues_run() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="D", slug="d2", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_delay_graph(60),
            published_at=datetime.now(timezone.utc),
            checksum="d2",
        )
        db.add(version)
        await db.commit()

        with patch("backend.modules.workflows.wait_persist.schedule_fast_wake"):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"prompt": "hi"},
                compile_context=CompileContext(require_publish_targets=False),
            )

        wait = (
            await db.execute(
                select(WorkflowWait).where(WorkflowWait.workflow_run_id == run.id)
            )
        ).scalar_one()
        wait.wake_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.flush()

        llm = MagicMock()
        llm.generate_text = AsyncMock(return_value="after")
        llm.provider_name = "mock"
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider", return_value=llm
        ):
            results = await wake_due_workflow_waits(db, enqueue_resume=False)

        assert results
        assert results[0]["outcome"] == "elapsed"
        refreshed = await engine.runs.get_run(tenant.id, run.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowRunStatus.SUCCEEDED.value
        wait2 = await db.get(WorkflowWait, wait.id)
        assert wait2 is not None
        assert wait2.status == WorkflowWaitStatus.RESOLVED.value
        assert wait2.resolved_outcome == "elapsed"
        await db.close()

    asyncio.run(_run())


def test_event_key_resolves_wait_atomically() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        graph = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {
                    "id": "wait",
                    "type": "wait",
                    "version": 1,
                    "config": {"event": "webhook", "timeout_seconds": 3600},
                },
                {
                    "id": "done",
                    "type": "generate_text",
                    "version": 1,
                    "config": {"max_tokens": 16},
                },
            ],
            "edges": [
                {"source": "trigger", "target": "wait"},
                {"source": "wait", "target": "done"},
            ],
        }
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="W", slug="w", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=graph,
            published_at=datetime.now(timezone.utc),
            checksum="w",
        )
        db.add(version)
        await db.commit()

        with patch("backend.modules.workflows.wait_persist.schedule_fast_wake"):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"prompt": "hi", "correlation_key": "evt-42"},
                compile_context=CompileContext(require_publish_targets=False),
            )
        assert run.status == WorkflowRunStatus.WAITING.value

        wait = await resolve_wait_by_event_key(
            db,
            tenant_id=tenant.id,
            event_key="evt-42",
            payload={"hello": "world"},
        )
        assert wait is not None
        assert wait.status == WorkflowWaitStatus.RESOLVED.value
        assert wait.resolved_outcome == "received"

        llm = MagicMock()
        llm.generate_text = AsyncMock(return_value="ok")
        llm.provider_name = "mock"
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider", return_value=llm
        ):
            resumed = await resume_waiting_node(
                engine,
                tenant.id,
                resume_token=wait.resume_token,
                outcome="received",
                decision={"event_payload": {"hello": "world"}},
            )
        assert resumed.status == WorkflowRunStatus.SUCCEEDED.value
        # Second resolve is a no-op.
        again = await resolve_wait_by_event_key(
            db, tenant_id=tenant.id, event_key="evt-42"
        )
        assert again is None
        await db.close()

    asyncio.run(_run())


def test_claim_due_waits_empty_when_not_due() -> None:
    async def _run() -> None:
        db = await _async_session()
        claimed = await claim_due_waits(db, batch_size=10)
        assert claimed == []
        await db.close()

    asyncio.run(_run())
