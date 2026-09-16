"""Phase 18 — workflow testing strategy gap coverage.

Covers: publish idempotency key, node retry attempt bump, tenant-scoped
run repo, end-to-end dry-run happy path, chess graph compile smoke.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.run_repository import WorkflowRunRepository


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _full_slice_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 64},
            },
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "generate"},
            {"source": "generate", "target": "approval"},
            {"source": "approval", "target": "publish", "condition": "approved"},
        ],
    }


def _chess_slice_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "chess",
                "type": "generate_chess_video",
                "version": 1,
                "config": {},
            },
            {"id": "approval", "type": "approval", "version": 1, "config": {}},
            {"id": "publish", "type": "publish", "version": 1, "config": {"dry_run": True}},
        ],
        "edges": [
            {"source": "trigger", "target": "chess"},
            {"source": "chess", "target": "approval"},
            {"source": "approval", "target": "publish", "condition": "approved"},
        ],
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
                        SocialAccount.__table__,
                        WorkflowDefinition.__table__,
                        WorkflowVersion.__table__,
                        Automation.__table__,
                        TaskExecution.__table__,
                        WorkflowRun.__table__,
                        WorkflowNodeRun.__table__,
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


async def _seed_published(
    db: AsyncSession, graph: dict[str, Any]
) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Strategy",
        slug=f"strategy-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(definition)
    await db.flush()
    version = WorkflowVersion(
        tenant_id=tenant.id,
        workflow_definition_id=definition.id,
        version=1,
        graph_json=graph,
        published_at=datetime.now(timezone.utc),
        checksum="strategy",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    await db.flush()
    return tenant, version


def test_publish_idempotency_key_from_run_id() -> None:
    run_id = uuid.uuid4()
    inputs = resolve_node_inputs(
        node_type="publish",
        trigger_payload={},
        initial_inputs={"content_job_id": str(uuid.uuid4())},
        upstream_outputs=[],
        run_id=run_id,
    )
    assert inputs["idempotency_key"] == f"wf-publish-{run_id}"


def test_publish_idempotency_key_prefers_explicit() -> None:
    run_id = uuid.uuid4()
    inputs = resolve_node_inputs(
        node_type="publish",
        trigger_payload={"idempotency_key": "explicit-publish-key"},
        initial_inputs={"content_job_id": str(uuid.uuid4())},
        upstream_outputs=[],
        run_id=run_id,
    )
    assert inputs["idempotency_key"] == "explicit-publish-key"


def test_run_repository_tenant_isolation() -> None:
    async def _run() -> None:
        db = await _async_session()
        t1, v1 = await _seed_published(db, _full_slice_graph())
        t2, v2 = await _seed_published(db, _full_slice_graph())
        repo = WorkflowRunRepository(db)
        r1 = WorkflowRun(
            tenant_id=t1.id,
            workflow_definition_id=v1.workflow_definition_id,
            workflow_version_id=v1.id,
            status=WorkflowRunStatus.QUEUED.value,
        )
        r2 = WorkflowRun(
            tenant_id=t2.id,
            workflow_definition_id=v2.workflow_definition_id,
            workflow_version_id=v2.id,
            status=WorkflowRunStatus.QUEUED.value,
        )
        await repo.add_run(r1)
        await repo.add_run(r2)
        listed = await repo.list_runs(t1.id)
        assert [row.id for row in listed] == [r1.id]
        assert await repo.get_run(t1.id, r2.id) is None
        await db.close()

    asyncio.run(_run())


def test_node_retry_increments_attempt() -> None:
    async def _run() -> None:
        db = await _async_session()
        graph = {
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
        tenant, version = await _seed_published(db, graph)
        engine = WorkflowEngine(db)
        calls = {"n": 0}

        async def _flaky_execute(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            calls["n"] += 1
            if calls["n"] == 1:
                return NodeResult(
                    status=NodeResultStatus.FAILED,
                    error={"code": "transient", "message": "boom"},
                )
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={"text": "recovered", "provider": "mock"},
            )

        with patch(
            "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
            new=_flaky_execute,
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "retry me"},
                mock_generation=False,
            )
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].status == WorkflowNodeRunStatus.FAILED.value
        assert nodes["generate"].attempt == 1
        assert run.status == WorkflowRunStatus.FAILED.value

        nodes["generate"].status = WorkflowNodeRunStatus.READY.value
        run.status = WorkflowRunStatus.RUNNING.value
        await db.flush()
        with patch(
            "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
            new=_flaky_execute,
        ):
            run = await engine.advance(tenant.id, run.id)
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].attempt == 2
        assert nodes["generate"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_e2e_dry_run_happy_path() -> None:
    """Brand-ready slice: mock gen → simulate approval → dry publish → succeeded."""

    async def _run() -> None:
        db = await _async_session()
        tenant, version = await _seed_published(db, _full_slice_graph())
        account_id = uuid.uuid4()
        job_id = uuid.uuid4()
        ctx = CompileContext(
            social_account_ids=[account_id],
            account_capabilities={str(account_id): ["llm", "publish"]},
        )

        async def _waiting_approval(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={"approval_request_id": str(uuid.uuid4()), "status": "pending"},
                waiting_reason="approval_pending",
            )

        publish_mock = MagicMock()
        publish_mock.publish_now = AsyncMock(
            return_value=[
                MagicMock(id=uuid.uuid4(), status="dry_run"),
            ]
        )

        with (
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=_waiting_approval,
            ),
            patch(
                "backend.modules.publishing.service.PublishingService",
                return_value=publish_mock,
            ),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                compile_context=ctx,
                dry_run=True,
                mock_generation=True,
                simulate_approval=True,
                trigger_payload={
                    "prompt": "daily tip",
                    "content_job_id": str(job_id),
                    "social_account_ids": [str(account_id)],
                },
            )

        assert run.trigger_type == "dry_run"
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].output_json.get("provider") == "mock"
        assert nodes["approval"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes["publish"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        publish_mock.publish_now.assert_awaited()
        call_kwargs = publish_mock.publish_now.await_args.kwargs
        assert call_kwargs["payload"].dry_run is True
        assert call_kwargs["payload"].idempotency_key == f"wf-publish-{run.id}"
        await db.close()

    asyncio.run(_run())


def test_chess_workflow_compiles() -> None:
    account_id = uuid.uuid4()
    result = WorkflowCompiler().validate_graph(
        _chess_slice_graph(),
        context=CompileContext(
            social_account_ids=[account_id],
            account_capabilities={
                str(account_id): ["video", "chess", "publish", "llm"]
            },
        ),
    )
    assert result.valid, [e.message for e in result.errors]
    assert result.normalized_graph is not None
    graph = result.normalized_graph
    nodes = graph["nodes"] if isinstance(graph, dict) else graph.nodes
    types = [n["type"] if isinstance(n, dict) else n.type for n in nodes]
    assert "generate_chess_video" in types
