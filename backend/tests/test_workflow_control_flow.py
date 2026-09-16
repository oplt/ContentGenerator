"""Phase 12 — control-flow nodes (condition / merge / delay / wait / fan-out)."""

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
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_resume import resume_waiting_node
from backend.modules.workflows.engine_unlock import cascade_skip, unlock_after_node_success
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodeResultStatus
from backend.modules.workflows.nodes.condition_node import ConditionNode
from backend.modules.workflows.nodes.merge_nodes import FanOutNode, MergeNode
from backend.modules.workflows.nodes.pause_nodes import DelayNode, WaitNode
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


def test_condition_emits_branch() -> None:
    node = ConditionNode()

    async def _run() -> None:
        result = await node.execute(
            build_node_context(tenant_id=uuid.uuid4()),
            node.validate_inputs({"risk_score": 0.9, "payload": {"risk_score": 0.9}}),
            node.validate_config(
                {"field": "risk_score", "operator": "gt", "compare_to": 0.5}
            ),
        )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["branch"] == "true"
        assert result.output["matched"] is True

    asyncio.run(_run())


def test_fan_out_normalizes_account_ids() -> None:
    node = FanOutNode()
    aid = uuid.uuid4()

    async def _run() -> None:
        result = await node.execute(
            build_node_context(tenant_id=uuid.uuid4()),
            node.validate_inputs({"social_account_ids": [aid]}),
            node.validate_config({"mode": "account_ids"}),
        )
        assert result.output["count"] == 1
        assert result.output["items"] == [str(aid)]

    asyncio.run(_run())


def test_merge_combines_sources() -> None:
    node = MergeNode()

    async def _run() -> None:
        result = await node.execute(
            build_node_context(tenant_id=uuid.uuid4()),
            node.validate_inputs(
                {"sources": [{"a": 1}, {"b": 2}], "bag": {"seed": True}}
            ),
            node.validate_config({"mode": "all"}),
        )
        assert result.output["merged"]["a"] == 1
        assert result.output["merged"]["b"] == 2
        assert result.output["seed"] is True

    asyncio.run(_run())


def test_unlock_branching_skips_other_arm() -> None:
    true_id = "arm_true"
    false_id = "arm_false"
    graph = WorkflowGraph.model_validate(
        {
            "nodes": [
                {"id": "cond", "type": "condition", "version": 1, "config": {}},
                {"id": true_id, "type": "summarize", "version": 1, "config": {}},
                {"id": false_id, "type": "summarize", "version": 1, "config": {}},
            ],
            "edges": [
                {"source": "cond", "target": true_id, "condition": "true"},
                {"source": "cond", "target": false_id, "condition": "false"},
            ],
        }
    )
    tid = uuid.uuid4()
    rid = uuid.uuid4()
    runs = {
        "cond": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="cond",
            node_type="condition",
            node_version=1,
            status=WorkflowNodeRunStatus.SUCCEEDED.value,
        ),
        true_id: WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id=true_id,
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
        false_id: WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id=false_id,
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
    }
    unlocked = unlock_after_node_success(
        "cond", graph=graph, node_runs=runs, output={"branch": "true"}
    )
    assert true_id in unlocked
    assert runs[true_id].status == WorkflowNodeRunStatus.READY.value
    assert runs[false_id].status == WorkflowNodeRunStatus.SKIPPED.value


def test_cascade_skip_descendants() -> None:
    graph = WorkflowGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "type": "summarize", "version": 1, "config": {}},
                {"id": "b", "type": "summarize", "version": 1, "config": {}},
            ],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    tid = uuid.uuid4()
    rid = uuid.uuid4()
    runs = {
        "a": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="a",
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
        "b": WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id="b",
            node_type="summarize",
            node_version=1,
            status=WorkflowNodeRunStatus.PENDING.value,
        ),
    }
    cascade_skip("a", graph=graph, node_runs=runs)
    assert runs["a"].status == WorkflowNodeRunStatus.SKIPPED.value
    assert runs["b"].status == WorkflowNodeRunStatus.SKIPPED.value


def test_compiler_rejects_condition_without_labels() -> None:
    result = WorkflowCompiler().validate_graph(
        {
            "nodes": [
                {"id": "t", "type": "manual_trigger", "version": 1, "config": {}},
                {"id": "c", "type": "condition", "version": 1, "config": {}},
                {"id": "a", "type": "summarize", "version": 1, "config": {}},
                {"id": "b", "type": "summarize", "version": 1, "config": {}},
            ],
            "edges": [
                {"source": "t", "target": "c"},
                {"source": "c", "target": "a"},
                {"source": "c", "target": "b"},
            ],
        }
    )
    assert result.valid is False
    assert any(e.code == "condition_edge_labels_required" for e in result.errors)


def test_delay_waits_without_celery_authority() -> None:
    node = DelayNode()
    token = str(uuid.uuid4())
    ctx = build_node_context(tenant_id=uuid.uuid4(), resume_token=token)

    async def _run() -> None:
        result = await node.execute(
            ctx,
            node.validate_inputs({}),
            node.validate_config({"duration_seconds": 30}),
        )
        assert result.status == NodeResultStatus.WAITING
        assert result.waiting_reason == "delay_until"
        assert result.output["resume_at"]

    asyncio.run(_run())


def test_wait_node_pending() -> None:
    node = WaitNode()

    async def _run() -> None:
        result = await node.execute(
            build_node_context(tenant_id=uuid.uuid4(), resume_token=str(uuid.uuid4())),
            node.validate_inputs({"correlation_key": "k1"}),
            node.validate_config({"event": "manual"}),
        )
        assert result.status == NodeResultStatus.WAITING
        assert result.output["status"] == "pending"

    asyncio.run(_run())


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


def _branch_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {
                "id": "cond",
                "type": "condition",
                "version": 1,
                "config": {"field": "value", "operator": "truthy"},
            },
            {
                "id": "yes",
                "type": "summarize",
                "version": 1,
                "config": {"max_words": 40},
            },
            {
                "id": "no",
                "type": "summarize",
                "version": 1,
                "config": {"max_words": 40},
            },
            {"id": "merge", "type": "merge", "version": 1, "config": {"mode": "all"}},
        ],
        "edges": [
            {"source": "trigger", "target": "cond"},
            {"source": "cond", "target": "yes", "condition": "true"},
            {"source": "cond", "target": "no", "condition": "false"},
            {"source": "yes", "target": "merge"},
            {"source": "no", "target": "merge"},
        ],
    }


def test_engine_condition_diamond_skips_false_arm() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Branch", slug="branch", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_branch_graph(),
            published_at=datetime.now(timezone.utc),
            checksum="x",
        )
        db.add(version)
        await db.commit()

        llm = MagicMock()
        llm.summarize = AsyncMock(return_value="ok")
        llm.provider_name = "mock"

        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider", return_value=llm
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"value": True, "text": "A long article about branching."},
                compile_context=CompileContext(require_publish_targets=False),
            )
        if run.status != WorkflowRunStatus.SUCCEEDED.value:
            nodes = await engine.runs.list_node_runs(tenant.id, run.id)
            detail = {n.node_id: (n.status, n.error_json) for n in nodes}
            raise AssertionError(f"run={run.status} nodes={detail}")
        nodes_by_id = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes_by_id["yes"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert nodes_by_id["no"].status == WorkflowNodeRunStatus.SKIPPED.value
        assert nodes_by_id["merge"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())


def test_resume_elapsed_outcome() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Delay", slug="delay", status="active"
        )
        db.add(definition)
        await db.flush()
        graph = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {
                    "id": "delay",
                    "type": "delay",
                    "version": 1,
                    "config": {"duration_seconds": 60},
                },
                {
                    "id": "done",
                    "type": "generate_text",
                    "version": 1,
                    "config": {"max_tokens": 32},
                },
            ],
            "edges": [
                {"source": "trigger", "target": "delay"},
                {"source": "delay", "target": "done"},
            ],
        }
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=graph,
            published_at=datetime.now(timezone.utc),
            checksum="d",
        )
        db.add(version)
        await db.commit()

        with patch("backend.modules.workflows.wait_store.schedule_fast_wake"):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"prompt": "hi"},
                compile_context=CompileContext(require_publish_targets=False),
            )
        assert run.status == WorkflowRunStatus.WAITING.value
        delay_run = next(
            n
            for n in await engine.runs.list_node_runs(tenant.id, run.id)
            if n.node_id == "delay"
        )
        assert delay_run.resume_token

        llm = MagicMock()
        llm.generate_text = AsyncMock(return_value="after")
        llm.provider_name = "mock"
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider", return_value=llm
        ):
            resumed = await resume_waiting_node(
                engine,
                tenant.id,
                resume_token=delay_run.resume_token,
                outcome="elapsed",
            )
        assert resumed.status == WorkflowRunStatus.SUCCEEDED.value
        await db.close()

    asyncio.run(_run())
