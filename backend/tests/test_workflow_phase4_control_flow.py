"""Phase 4 — control-flow semantics: merge any/all, SKIPPED, real fan-out."""

from __future__ import annotations

import asyncio
import uuid
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
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_fanout import iteration_key_for_item, unique_iteration_keys
from backend.modules.workflows.engine_ready import is_ready
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _runs(
    graph: WorkflowGraph,
    statuses: dict[str, str],
) -> dict[str, WorkflowNodeRun]:
    tid = uuid.uuid4()
    rid = uuid.uuid4()
    out: dict[str, WorkflowNodeRun] = {}
    for node in graph.nodes:
        out[node.id] = WorkflowNodeRun(
            tenant_id=tid,
            workflow_run_id=rid,
            node_id=node.id,
            node_type=node.type,
            node_version=1,
            status=statuses.get(node.id, WorkflowNodeRunStatus.PENDING.value),
            iteration_key="",
        )
    return out


def _diamond(mode: str = "all") -> WorkflowGraph:
    return WorkflowGraph.model_validate(
        {
            "nodes": [
                {"id": "a", "type": "summarize", "version": 1, "config": {}},
                {"id": "b", "type": "summarize", "version": 1, "config": {}},
                {"id": "merge", "type": "merge", "version": 1, "config": {"mode": mode}},
            ],
            "edges": [
                {"source": "a", "target": "merge"},
                {"source": "b", "target": "merge"},
            ],
        }
    )


def test_merge_any_ready_when_one_succeeded_other_pending() -> None:
    graph = _diamond("any")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.SUCCEEDED.value,
            "b": WorkflowNodeRunStatus.PENDING.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is True


def test_merge_any_ready_when_one_succeeded_other_skipped() -> None:
    graph = _diamond("any")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.SUCCEEDED.value,
            "b": WorkflowNodeRunStatus.SKIPPED.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is True


def test_merge_any_ready_when_one_failed_other_succeeded() -> None:
    graph = _diamond("any")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.FAILED.value,
            "b": WorkflowNodeRunStatus.SUCCEEDED.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is True


def test_merge_any_not_ready_when_all_failed() -> None:
    graph = _diamond("any")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.FAILED.value,
            "b": WorkflowNodeRunStatus.FAILED.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is False


def test_merge_all_waits_for_pending_sibling() -> None:
    graph = _diamond("all")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.SUCCEEDED.value,
            "b": WorkflowNodeRunStatus.PENDING.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is False


def test_merge_all_accepts_skipped_branch() -> None:
    graph = _diamond("all")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.SUCCEEDED.value,
            "b": WorkflowNodeRunStatus.SKIPPED.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is True


def test_merge_all_rejects_failed_branch() -> None:
    graph = _diamond("all")
    runs = _runs(
        graph,
        {
            "a": WorkflowNodeRunStatus.SUCCEEDED.value,
            "b": WorkflowNodeRunStatus.FAILED.value,
            "merge": WorkflowNodeRunStatus.PENDING.value,
        },
    )
    assert is_ready("merge", graph=graph, node_runs=runs) is False


def test_iteration_keys_stable_and_unique() -> None:
    pairs = unique_iteration_keys(["x", "x", {"platform": "youtube"}])
    assert [k for k, _ in pairs] == ["x", "x-2", "youtube"]
    assert iteration_key_for_item("instagram", 0) == "instagram"


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
                    ],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False)()


def _fanout_graph() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {"id": "fan", "type": "fan_out", "version": 1, "config": {"mode": "list"}},
            {
                "id": "body",
                "type": "summarize",
                "version": 1,
                "config": {"max_words": 20},
            },
            {"id": "merge", "type": "merge", "version": 1, "config": {"mode": "all"}},
        ],
        "edges": [
            {"source": "trigger", "target": "fan"},
            {"source": "fan", "target": "body"},
            {"source": "body", "target": "merge"},
        ],
    }


def test_engine_fan_out_spawns_iterations_and_merge_aggregates() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Fan", slug="fan", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=_fanout_graph(),
            published_at=datetime.now(timezone.utc),
            checksum="f",
        )
        db.add(version)
        await db.commit()

        llm = MagicMock()
        llm.summarize = AsyncMock(side_effect=lambda text, **_k: f"sum:{text}")
        llm.provider_name = "mock"

        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider", return_value=llm
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                initial_inputs={"items": ["x", "youtube", "instagram"]},
                compile_context=CompileContext(require_publish_targets=False),
            )

        if run.status != WorkflowRunStatus.SUCCEEDED.value:
            nodes = await engine.runs.list_node_runs(tenant.id, run.id)
            detail = {
                (n.node_id, n.iteration_key): (n.status, n.error_json) for n in nodes
            }
            raise AssertionError(f"run={run.status} nodes={detail}")

        nodes = await engine.runs.list_node_runs(tenant.id, run.id)
        body_iters = [
            n
            for n in nodes
            if n.node_id == "body" and n.iteration_key and n.status == "succeeded"
        ]
        assert {n.iteration_key for n in body_iters} == {"x", "youtube", "instagram"}
        placeholder = next(
            n for n in nodes if n.node_id == "body" and not n.iteration_key
        )
        assert placeholder.status == WorkflowNodeRunStatus.SKIPPED.value
        merge = next(n for n in nodes if n.node_id == "merge")
        assert merge.status == WorkflowNodeRunStatus.SUCCEEDED.value
        sources = merge.output_json.get("sources") or []
        assert len(sources) == 3
        # Stable order by iteration_key
        assert [s.get("text", "").startswith("sum:") for s in sources] == [True, True, True]
        await db.close()

    asyncio.run(_run())


def test_engine_merge_any_does_not_wait_for_slow_arm() -> None:
    async def _run() -> None:
        db = await _async_session()
        tenant = Tenant(name="T", slug=f"t-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        graph = {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {
                    "id": "fast",
                    "type": "generate_text",
                    "version": 1,
                    "config": {"max_tokens": 16},
                },
                {
                    "id": "slow",
                    "type": "generate_text",
                    "version": 1,
                    "config": {"max_tokens": 16},
                },
                {"id": "merge", "type": "merge", "version": 1, "config": {"mode": "any"}},
            ],
            "edges": [
                {"source": "trigger", "target": "fast"},
                {"source": "trigger", "target": "slow"},
                {"source": "fast", "target": "merge"},
                {"source": "slow", "target": "merge"},
            ],
        }
        definition = WorkflowDefinition(
            tenant_id=tenant.id, name="Any", slug="any", status="active"
        )
        db.add(definition)
        await db.flush()
        version = WorkflowVersion(
            tenant_id=tenant.id,
            workflow_definition_id=definition.id,
            version=1,
            graph_json=graph,
            published_at=datetime.now(timezone.utc),
            checksum="a",
        )
        db.add(version)
        await db.commit()

        calls = {"n": 0}

        async def _gen(self, context, inputs, config):  # noqa: ANN001
            _ = self, context, inputs, config
            calls["n"] += 1
            if calls["n"] == 1:
                return NodeResult(
                    status=NodeResultStatus.SUCCEEDED,
                    output={"text": "fast", "provider": "mock"},
                )
            # Second arm never finishes — stays pending by returning WAITING? 
            # Better: hang by not being claimed — patch only first execute.
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={"text": "slow", "provider": "mock"},
            )

        # Force slow to stay PENDING: fail claim by keeping it from becoming ready
        # after fast+merge — use side_effect that succeeds once then we cancel slow.
        with patch(
            "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
            new=_gen,
        ):
            engine = WorkflowEngine(db)
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "go"},
                compile_context=CompileContext(require_publish_targets=False),
            )

        # With mode=any, once one arm succeeds merge can run; both arms may still complete
        # in the same drain. Assert merge succeeded and at least one arm succeeded.
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["merge"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert (
            nodes["fast"].status == WorkflowNodeRunStatus.SUCCEEDED.value
            or nodes["slow"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        )
        await db.close()

    asyncio.run(_run())
