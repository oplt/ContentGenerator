"""Phase 5 — minimal linear workflow engine."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import Table, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.content_strategy.models import Brand
from backend.modules.identity_access.models import Tenant
from backend.modules.operations.models import TaskExecution
from backend.modules.publishing.models import SocialAccount
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
)


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
                        WorkflowWait.__table__,
                    ],
                ),
            )
        )

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return Session()


async def _seed_published(
    db: AsyncSession, graph: dict[str, Any]
) -> tuple[Tenant, WorkflowVersion]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    db.add(tenant)
    await db.flush()
    definition = WorkflowDefinition(
        tenant_id=tenant.id,
        name="Engine",
        slug=f"engine-{uuid.uuid4().hex[:8]}",
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
        checksum="test",
    )
    db.add(version)
    await db.flush()
    definition.current_version_id = version.id
    await db.flush()
    return tenant, version


def _mock_llm(*, text: str = "hello generated") -> Any:
    llm = AsyncMock()
    llm.generate_text = AsyncMock(return_value=text)
    llm.provider_name = "mock"
    return llm


def test_engine_runs_trigger_then_generate_text() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, version = await _seed_published(db, _trigger_generate_graph())
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(text="hello workflow engine"),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "hello workflow engine"},
                correlation_id="corr-engine-1",
            )
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        by_id = {n.node_id: n for n in nodes}
        assert by_id["trigger"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert by_id["generate"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert "hello" in str(by_id["generate"].output_json.get("text", ""))
        await db.close()

    asyncio.run(_run())


def test_engine_idempotent_on_correlation_and_succeeded_nodes() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, version = await _seed_published(db, _trigger_generate_graph())
        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm(text="once"),
        ):
            first = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "once"},
                correlation_id="corr-idem",
            )
            second = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "once"},
                correlation_id="corr-idem",
            )
        assert first.id == second.id
        before = {
            n.node_id: n.attempt for n in await engine.runs.list_node_runs(tenant.id, first.id)
        }
        await engine.advance(tenant.id, first.id)
        after = {
            n.node_id: n.attempt for n in await engine.runs.list_node_runs(tenant.id, first.id)
        }
        assert before == after
        await db.close()

    asyncio.run(_run())


def test_engine_pauses_on_approval_waiting() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant, version = await _seed_published(db, _full_slice_graph())
        ctx = CompileContext(require_publish_targets=False)

        async def _waiting_execute(context, inputs, config):  # type: ignore[no-untyped-def]
            _ = (context, inputs, config)
            return NodeResult(
                status=NodeResultStatus.WAITING,
                output={
                    "approval_request_id": str(uuid.uuid4()),
                    "status": "pending",
                    "channels": [],
                    "content_job_id": str(uuid.uuid4()),
                },
                waiting_reason="approval_pending",
            )

        with (
            patch(
                "backend.modules.workflows.nodes.text.get_llm_provider",
                return_value=_mock_llm(text="need approval"),
            ),
            patch(
                "backend.modules.workflows.nodes.approval.ApprovalNode.execute",
                new=AsyncMock(side_effect=_waiting_execute),
            ),
            patch("backend.modules.workflows.wait_persist.schedule_fast_wake"),
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={
                    "prompt": "need approval",
                    "content_job_id": str(uuid.uuid4()),
                },
                compile_context=ctx,
                correlation_id="corr-wait",
            )

        assert run.status == WorkflowRunStatus.WAITING.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes["approval"].status == WorkflowNodeRunStatus.WAITING.value
        assert nodes["approval"].resume_token
        assert nodes["publish"].status == WorkflowNodeRunStatus.PENDING.value
        await db.close()

    asyncio.run(_run())


def test_engine_rejects_unpublished_version() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Draft", slug=f"draft-{uuid.uuid4().hex[:8]}"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_trigger_generate_graph(),
            published_at=None,
        )
        db.add(version)
        await db.flush()

        engine = WorkflowEngine(db)
        with pytest.raises(HTTPException) as exc:
            await engine.start_run(tenant_id=tenant.id, workflow_version_id=version.id)
        assert exc.value.status_code == 400
        await db.close()

    asyncio.run(_run())
