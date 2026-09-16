"""Phase 3 — port/binding DAG data flow (schema_version >= 2)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

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
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.graph_schema import GraphEdge, GraphNode, InputBinding, WorkflowGraph
from backend.modules.workflows.models import Automation, WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import NodePort
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


def test_port_edge_maps_source_to_target() -> None:
    graph = WorkflowGraph(
        schema_version=2,
        nodes=[
            GraphNode(id="a", type="generate_text", version=1),
            GraphNode(id="b", type="summarize", version=1),
        ],
        edges=[GraphEdge.model_validate(
            {
                "source": "a",
                "target": "b",
                "source_port": "text",
                "target_port": "text",
            }
        )
        ],
    )
    inputs = resolve_node_inputs(
        node_type="summarize",
        trigger_payload={},
        initial_inputs={},
        upstream_outputs=[{"text": "hello world", "provider": "mock"}],
        schema_version=2,
        graph=graph,
        graph_node=graph.nodes[1],
        node_outputs={"a": {"text": "hello world", "provider": "mock"}},
        input_ports=[NodePort(name="text", data_type="string")],
    )
    assert inputs == {"text": "hello world"}


def test_input_binding_from_trigger_path() -> None:
    graph = WorkflowGraph(
        schema_version=2,
        nodes=[
            GraphNode(
                id="gen",
                type="generate_text",
                version=1,
                input_bindings={
                    "prompt": InputBinding(source="trigger", path="topic"),
                    "system_hint": InputBinding(source="constant", value="be brief"),
                },
            )
        ],
        edges=[],
    )
    inputs = resolve_node_inputs(
        node_type="generate_text",
        trigger_payload={"topic": "chess openings"},
        initial_inputs={},
        upstream_outputs=[],
        schema_version=2,
        graph=graph,
        graph_node=graph.nodes[0],
        node_outputs={},
        input_ports=[
            NodePort(name="prompt", data_type="string"),
            NodePort(name="system_hint", data_type="string", required=False),
        ],
    )
    assert inputs["prompt"] == "chess openings"
    assert inputs["system_hint"] == "be brief"


def test_legacy_schema_version_one_still_aliases() -> None:
    inputs = resolve_node_inputs(
        node_type="generate_chess_video",
        trigger_payload={},
        initial_inputs={"pgn": "1. e4 e5"},
        upstream_outputs=[],
        schema_version=1,
    )
    assert inputs["source_text"] == "1. e4 e5"


def test_engine_inputs_facade_has_no_node_type_switches() -> None:
    from pathlib import Path
    import re

    source = Path(
        "/home/polat/Desktop/Projects/content_generator/backend/modules/workflows/engine_inputs.py"
    ).read_text(encoding="utf-8")
    assert not re.findall(r'if\s+node_type\s*==\s*"', source)


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
    return async_sessionmaker(engine, expire_on_commit=False)()


def _v2_graph() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "nodes": [
            {
                "id": "trigger",
                "type": "manual_trigger",
                "version": 1,
                "config": {},
                "input_bindings": {
                    "payload": {"source": "trigger"},
                },
            },
            {
                "id": "generate",
                "type": "generate_text",
                "version": 1,
                "config": {"max_tokens": 32},
                "input_bindings": {
                    "prompt": {"source": "trigger", "path": "prompt"},
                },
            },
        ],
        "edges": [
            {
                "source": "trigger",
                "target": "generate",
                "source_port": "payload",
                "target_port": "prompt",
            }
        ],
    }


def _mock_llm(text: str = "ported") -> MagicMock:
    llm = MagicMock()

    async def _agen(*_a, **_k):  # type: ignore[no-untyped-def]
        return text

    llm.generate_text = _agen
    llm.provider_name = "mock"
    return llm


def test_schema_v2_run_executes_with_bindings() -> None:
    async def _run() -> None:
        db = await _session()
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
            graph_json=_v2_graph(),
            published_at=datetime.now(timezone.utc),
        )
        db.add(version)
        await db.flush()

        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.get_llm_provider",
            return_value=_mock_llm("ported"),
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "hello ports"},
                advance=True,
            )
        assert run.status == WorkflowRunStatus.SUCCEEDED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].status == WorkflowNodeRunStatus.SUCCEEDED.value
        assert "ported" in str(nodes["generate"].output_json.get("text", ""))
        # Binding/path prompt used (edge mapped payload object into prompt would fail validate;
        # binding path wins for prompt).
        assert nodes["generate"].input_json.get("prompt") == "hello ports"
        await db.close()

    asyncio.run(_run())


def test_invalid_output_fails_permanently() -> None:
    async def _run() -> None:
        db = await _session()
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
            graph_json={
                "schema_version": 1,
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
            },
            published_at=datetime.now(timezone.utc),
        )
        db.add(version)
        await db.flush()

        from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus

        async def _bad_out(self, context, inputs, config):  # type: ignore[no-untyped-def]
            _ = (self, context, inputs, config)
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output={"not_text": True},
            )

        engine = WorkflowEngine(db)
        with patch(
            "backend.modules.workflows.nodes.text.GenerateTextNode.execute",
            new=_bad_out,
        ):
            run = await engine.start_run(
                tenant_id=tenant.id,
                workflow_version_id=version.id,
                trigger_payload={"prompt": "x"},
                advance=True,
            )
        assert run.status == WorkflowRunStatus.FAILED.value
        nodes = {n.node_id: n for n in await engine.runs.list_node_runs(tenant.id, run.id)}
        assert nodes["generate"].error_class == "permanent"
        assert (nodes["generate"].error_json or {}).get("code") == "invalid_node_output"
        await db.close()

    asyncio.run(_run())
