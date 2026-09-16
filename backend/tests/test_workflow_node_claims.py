"""Phase 1 — durable node claims, concurrency, and crash recovery."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import settings
from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_node_task import execute_claimed_node_run
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.node_recovery import recover_stale_workflow_node_runs
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows import run_repository as node_claims


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 32},
            },
        ],
        "edges": [{"source": "trigger", "target": "generate"}],
    }


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE users (id CHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(list[Table], [
                    Tenant.__table__,
                    Brand.__table__,
                    SocialAccount.__table__,
                    WorkflowDefinition.__table__,
                    WorkflowVersion.__table__,
                    Automation.__table__,
                    TaskExecution.__table__,
                    WorkflowRun.__table__,
                    WorkflowNodeRun.__table__,
                ]),
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker()


async def _seed(db: AsyncSession) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id, name="W", slug=f"w-{uuid.uuid4().hex[:8]}"
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json=_graph(),
        published_at=datetime.now(timezone.utc),
    )
    db.add(version)
    await db.flush()
    return tenant, version


def _mock_llm(text: str = "ok") -> MagicMock:
    llm = MagicMock()

    async def _agen(*_a, **_k):  # type: ignore[no-untyped-def]
        return text

    llm.generate_text = _agen
    llm.provider_name = "mock"
    return llm


def test_two_claimers_cannot_claim_same_ready_node() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "x"},
                advance=False,
            )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        trigger = next(n for n in nodes if n.node_id == "trigger")
        assert trigger.status == WorkflowNodeRunStatus.READY.value

        first = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        second = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert first is not None
        assert first.claim_token
        assert second is None
        await db.close()

    asyncio.run(_run())


def test_stale_running_node_is_requeued_by_recovery() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            trigger_payload={"prompt": "x"},
            advance=False,
        )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        trigger = next(n for n in nodes if n.node_id == "trigger")
        claimed = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert claimed is not None
        await node_claims.begin_node_execution(
            db,
            tenant_id=tenant.id,
            node_run_id=claimed.id,
            claim_token=str(claimed.claim_token),
            worker_task_id="dead-worker",
            task_execution_id=None,
        )
        # Expire lease without completing.
        stale = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert stale is not None
        stale.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        stale.attempt = 1
        await db.flush()

        recovered = await recover_stale_workflow_node_runs(db, enqueue_advance=False)
        assert recovered
        assert recovered[0]["action"] == "requeued"
        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowNodeRunStatus.READY.value
        assert refreshed.claim_token is None
        await db.close()

    asyncio.run(_run())


def test_stale_node_fails_after_max_attempts() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        run = await engine.start_run(
            tenant_id=tenant.id,
            workflow_version_id=version.id,
            trigger_payload={"prompt": "x"},
            advance=False,
        )
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        trigger = next(n for n in nodes if n.node_id == "trigger")
        claimed = await node_claims.claim_ready_node(
            db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
        )
        assert claimed is not None
        await node_claims.begin_node_execution(
            db,
            tenant_id=tenant.id,
            node_run_id=claimed.id,
            claim_token=str(claimed.claim_token),
            worker_task_id="dead",
            task_execution_id=None,
        )
        stale = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert stale is not None
        stale.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        stale.attempt = 99
        await db.flush()

        recovered = await recover_stale_workflow_node_runs(db, enqueue_advance=False)
        assert recovered[0]["action"] == "failed"
        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert refreshed is not None
        assert refreshed.status == WorkflowNodeRunStatus.FAILED.value
        await db.close()

    asyncio.run(_run())


def test_execute_claimed_node_links_task_execution_id() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        engine = WorkflowEngine(db)
        te = TaskExecution(
            task_name="execute_workflow_node",
            queue_name="generation",
            status="running",
            tenant_id=tenant.id,
            entity_type="workflow_node_run",
            celery_task_id="celery-1",
        )
        db.add(te)
        await db.flush()

        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm("linked"),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "linked"},
                advance=False,
            )
            nodes = await engine.runs.list_node_runs(tenant.id, run.id)
            trigger = next(n for n in nodes if n.node_id == "trigger")
            claimed = await node_claims.claim_ready_node(
                db, tenant_id=tenant.id, workflow_run_id=run.id, node_run_id=trigger.id
            )
            assert claimed is not None
            await execute_claimed_node_run(
                engine,
                tenant_id=tenant.id,
                workflow_run_id=run.id,
                node_run_id=claimed.id,
                claim_token=str(claimed.claim_token),
                worker_task_id="celery-1",
                task_execution_id=te.id,
                enqueue_followups=False,
            )

        refreshed = await engine.runs.get_node_run_by_id(tenant.id, claimed.id)
        assert refreshed is not None
        assert refreshed.task_execution_id == te.id
        assert str(te.id) in (refreshed.task_execution_ids or [])
        assert refreshed.status == WorkflowNodeRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_celery_path_enqueues_execute_task_not_inline() -> None:
    async def _run() -> None:
        db = await _session()
        tenant, version = await _seed(db)
        delayed: list[dict[str, str]] = []

        class _FakeTask:
            def delay(self, **kwargs: str) -> None:
                delayed.append(kwargs)

        with (
            patch.object(settings, "WORKFLOW_INLINE_NODE_EXECUTION", False),
            patch("backend.workers.tasks.execute_workflow_node_task", _FakeTask()),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "queued"},
                advance=True,
            )
            nodes = await engine.runs.list_node_runs(tenant.id, run.id)
            by_id = {n.node_id: n for n in nodes}
            assert by_id["trigger"].status == WorkflowNodeRunStatus.QUEUED.value
            assert by_id["trigger"].claim_token
            assert delayed
            assert delayed[0]["node_run_id"] == str(by_id["trigger"].id)
            assert run.status == WorkflowRunStatus.RUNNING.value
        await db.close()

    asyncio.run(_run())
