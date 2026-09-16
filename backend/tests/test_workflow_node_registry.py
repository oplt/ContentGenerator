"""Phase 2 — workflow node contract + registry."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.nodes import ALL_NODE_TYPES, IMPLEMENTED_SLICE
from backend.modules.workflows.nodes.base import (
    NodeResultStatus,
    WorkflowNodeNotFoundError,
    WorkflowNodeNotImplementedError,
)
from backend.modules.workflows.nodes.text import GenerateTextConfig, GenerateTextNode
from backend.modules.workflows.nodes.triggers import ManualTriggerNode
from backend.modules.workflows.registry import (
    WorkflowNodeRegistry,
    build_default_registry,
    reset_default_registry,
)
from backend.modules.workflows.service import WorkflowService


@pytest.fixture(autouse=True)
def _fresh_registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


def test_registry_lists_all_registered_nodes() -> None:
    registry = build_default_registry()
    nodes = registry.list_nodes()
    types = {n.type for n in nodes}
    assert "manual_trigger" in types
    assert "generate_text" in types
    assert "approval" in types
    assert "publish" in types
    assert len(nodes) == len(ALL_NODE_TYPES)


def test_registry_rejects_unknown_node_type() -> None:
    registry = build_default_registry()
    with pytest.raises(WorkflowNodeNotFoundError):
        registry.get("not_a_real_node")


def test_node_config_validated_by_pydantic() -> None:
    node = GenerateTextNode()
    ok = node.validate_config({"max_tokens": 100, "temperature": 0.2})
    assert isinstance(ok, GenerateTextConfig)
    assert ok.max_tokens == 100
    with pytest.raises(ValidationError):
        node.validate_config({"max_tokens": 1})  # below ge=16


def test_node_schemas_are_machine_readable() -> None:
    definition = WorkflowService().get_node("generate_text")
    assert definition.config_schema["type"] == "object"
    assert "max_tokens" in definition.config_schema["properties"]
    assert definition.input_schema["properties"]["prompt"]["type"] == "string"
    assert definition.may_pause is False
    assert WorkflowService().get_node("approval").may_pause is True


def test_compiler_rejects_unknown_node_types() -> None:
    result = WorkflowCompiler().validate_graph(
        {
            "nodes": [
                {"id": "t", "type": "manual_trigger", "version": 1, "config": {}},
                {"id": "x", "type": "does_not_exist", "version": 1, "config": {}},
            ]
        }
    )
    assert result.valid is False
    assert any(e.code == "unknown_node_type" for e in result.errors)


def test_compiler_rejects_invalid_config() -> None:
    result = WorkflowCompiler().validate_graph(
        {
            "nodes": [
                {
                    "id": "g",
                    "type": "generate_text",
                    "version": 1,
                    "config": {"max_tokens": 1},
                }
            ]
        }
    )
    assert result.valid is False
    assert any(e.code == "invalid_config" for e in result.errors)


def test_manual_trigger_execute() -> None:
    node = ManualTriggerNode()
    context = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        result = await node.execute(
            context,
            node.validate_inputs({"payload": {"source": "api"}}),
            node.validate_config({}),
        )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["payload"] == {"source": "api"}
        assert result.output["trigger_type"] == "manual"

    asyncio.run(_run())


def test_stub_node_raises_not_implemented() -> None:
    node = build_default_registry().get("research_sources")
    context = build_node_context(tenant_id=uuid.uuid4())

    async def _run() -> None:
        with pytest.raises(WorkflowNodeNotImplementedError):
            await node.execute(context, node.validate_inputs({}), node.validate_config({}))

    asyncio.run(_run())


def test_implemented_slice_nodes_present() -> None:
    registry = WorkflowNodeRegistry()
    for cls in IMPLEMENTED_SLICE:
        registry.register(cls)
    types = {n.type for n in registry.list_nodes()}
    assert "manual_trigger" in types
    assert "generate_text" in types
    assert "generate_chess_video" in types
    assert "platform_transform" in types
    assert "approval" in types
    assert "publish" in types
    assert len(types) == len(IMPLEMENTED_SLICE)


def test_service_validate_node_config_reports_errors() -> None:
    response = WorkflowService().validate_node_config(
        "generate_text", {"temperature": 9.0}
    )
    assert response.valid is False
    assert response.errors
