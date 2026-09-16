"""In-process registry of typed workflow nodes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.modules.workflows.nodes.base import (
    WorkflowNode,
    WorkflowNodeNotFoundError,
)
from backend.modules.workflows.schemas import (
    NodeDefinitionResponse,
    NodePortResponse,
    RetryPolicyResponse,
)


class WorkflowNodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[int, WorkflowNode[Any, Any, Any]]] = {}

    def register(self, node: WorkflowNode[Any, Any, Any] | type[WorkflowNode[Any, Any, Any]]) -> None:
        instance: WorkflowNode[Any, Any, Any] = node() if isinstance(node, type) else node
        versions = self._nodes.setdefault(instance.type, {})
        if instance.version in versions:
            raise ValueError(
                f"Node '{instance.type}' version {instance.version} already registered"
            )
        versions[instance.version] = instance

    def get(self, node_type: str, version: int | None = None) -> WorkflowNode[Any, Any, Any]:
        versions = self._nodes.get(node_type)
        if not versions:
            raise WorkflowNodeNotFoundError(f"Unknown workflow node type: {node_type}")
        if version is None:
            return versions[max(versions)]
        try:
            return versions[version]
        except KeyError as exc:
            raise WorkflowNodeNotFoundError(
                f"Unknown workflow node type/version: {node_type}@v{version}"
            ) from exc

    def has(self, node_type: str, version: int | None = None) -> bool:
        try:
            self.get(node_type, version)
            return True
        except WorkflowNodeNotFoundError:
            return False

    def list_nodes(self) -> list[WorkflowNode[Any, Any, Any]]:
        nodes: list[WorkflowNode[Any, Any, Any]] = []
        for versions in self._nodes.values():
            nodes.extend(versions[v] for v in sorted(versions))
        return sorted(nodes, key=lambda n: (n.category, n.type, n.version))

    def list_definitions(self) -> list[NodeDefinitionResponse]:
        return [self.to_definition(node) for node in self.list_nodes()]

    def to_definition(self, node: WorkflowNode[Any, Any, Any]) -> NodeDefinitionResponse:
        return NodeDefinitionResponse(
            type=node.type,
            version=node.version,
            category=node.category,
            display_name=node.display_name,
            description=node.description,
            input_ports=[
                NodePortResponse(
                    name=p.name,
                    data_type=p.data_type,
                    required=p.required,
                    description=p.description,
                )
                for p in node.input_ports
            ],
            output_ports=[
                NodePortResponse(
                    name=p.name,
                    data_type=p.data_type,
                    required=p.required,
                    description=p.description,
                )
                for p in node.output_ports
            ],
            config_schema=node.ConfigSchema.model_json_schema(),
            input_schema=node.InputSchema.model_json_schema(),
            output_schema=node.OutputSchema.model_json_schema(),
            required_capabilities=list(node.required_capabilities),
            is_asynchronous=node.is_asynchronous,
            may_pause=node.may_pause,
            retry_policy=RetryPolicyResponse(
                max_attempts=node.retry_policy.max_attempts,
                backoff_seconds=node.retry_policy.backoff_seconds,
                retry_on=list(node.retry_policy.retry_on),
            ),
        )


_default_registry: WorkflowNodeRegistry | None = None


def register_many(
    registry: WorkflowNodeRegistry,
    nodes: Iterable[WorkflowNode[Any, Any, Any] | type[WorkflowNode[Any, Any, Any]]],
) -> WorkflowNodeRegistry:
    for node in nodes:
        registry.register(node)
    return registry


def build_default_registry() -> WorkflowNodeRegistry:
    from backend.modules.workflows.nodes import ALL_NODE_TYPES

    return register_many(WorkflowNodeRegistry(), ALL_NODE_TYPES)


def get_default_registry() -> WorkflowNodeRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry


def reset_default_registry(registry: WorkflowNodeRegistry | None = None) -> None:
    """Test helper to swap/clear the process-wide registry."""

    global _default_registry
    _default_registry = registry
