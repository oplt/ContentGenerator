"""Phase 12 — node implementation availability metadata + compiler gate."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.nodes.base import NodeImplementationStatus
from backend.modules.workflows.nodes import IMPLEMENTED_SLICE
from backend.modules.workflows.registry import build_default_registry, reset_default_registry


@pytest.fixture(autouse=True)
def _registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def _ctx() -> CompileContext:
    account_id = uuid.uuid4()
    return CompileContext(
        social_account_ids=[account_id],
        account_capabilities={str(account_id): ["llm", "publish"]},
        require_publish_targets=False,
        require_approval_before_publish=False,
    )


def test_registry_exposes_implementation_status() -> None:
    registry = build_default_registry()
    defs = {d.type: d for d in registry.list_definitions()}
    assert defs["generate_text"].implementation_status == "stable"
    assert defs["generate_text"].executable is True
    assert defs["schedule_trigger"].implementation_status == "unavailable"
    assert defs["schedule_trigger"].executable is False
    assert defs["webhook_trigger"].implementation_status == "stable"
    assert defs["webhook_trigger"].executable is True
    assert defs["research_sources"].executable is True
    assert defs["fetch_metrics"].executable is True
    assert defs["generate_canonical_content"].implementation_status == "beta"


def test_unavailable_node_compile_error_node_not_executable() -> None:
    result = WorkflowCompiler().validate_graph(
        {
            "nodes": [
                {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
                {
                    "id": "sched",
                    "type": "schedule_trigger",
                    "version": 1,
                    "config": {},
                },
                {"id": "gen", "type": "generate_text", "version": 1, "config": {}},
            ],
            "edges": [
                {"source": "trigger", "target": "gen"},
                {"source": "sched", "target": "gen"},
            ],
        },
        _ctx(),
    )
    assert result.valid is False
    assert any(e.code == "node_not_executable" for e in result.errors)
    assert any(e.node_type == "schedule_trigger" for e in result.errors)


def test_executable_research_and_metrics_in_implemented_slice() -> None:
    types = {cls.type for cls in IMPLEMENTED_SLICE}
    assert "research_sources" in types
    assert "fetch_metrics" in types
    assert "schedule_trigger" not in types
    assert "webhook_trigger" in types


def test_make_stub_status_is_explicit_not_classname() -> None:
    node = build_default_registry().get("schedule_trigger")
    assert node.implementation_status is NodeImplementationStatus.UNAVAILABLE
    assert "Stub" not in node.type
    assert node.is_executable() is False


def test_graph_with_only_stable_nodes_compiles() -> None:
    graph = {
        "nodes": [
            {"id": "trigger", "type": "manual_trigger", "version": 1, "config": {}},
            {"id": "gen", "type": "generate_text", "version": 1, "config": {}},
            {"id": "metrics", "type": "fetch_metrics", "version": 1, "config": {"sync": False}},
        ],
        "edges": [
            {"source": "trigger", "target": "gen"},
            {"source": "gen", "target": "metrics"},
        ],
    }
    result = WorkflowCompiler().validate_graph(graph, _ctx())
    assert result.valid is True, [e.model_dump() for e in result.errors]
