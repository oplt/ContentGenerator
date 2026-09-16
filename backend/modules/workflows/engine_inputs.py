"""Resolve workflow node inputs.

schema_version == 1 → legacy node-type router (historical graphs only)
schema_version >= 2 → port/binding resolver (no node-type switches)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.modules.workflows.engine_inputs_bag import merge_upstream_bag
from backend.modules.workflows.engine_inputs_legacy import resolve_legacy_node_inputs
from backend.modules.workflows.engine_inputs_ports import resolve_ports_and_bindings
from backend.modules.workflows.graph_schema import GraphNode, WorkflowGraph
from backend.modules.workflows.nodes.base import NodePort

__all__ = ["merge_upstream_bag", "resolve_node_inputs", "graph_schema_version"]


def graph_schema_version(graph: WorkflowGraph | dict[str, Any] | None) -> int:
    if graph is None:
        return 1
    if isinstance(graph, WorkflowGraph):
        return int(graph.schema_version or 1)
    return int(graph.get("schema_version") or 1)


def resolve_node_inputs(
    *,
    node_type: str,
    trigger_payload: dict[str, Any],
    initial_inputs: dict[str, Any],
    upstream_outputs: list[dict[str, Any]],
    run_id: UUID | None = None,
    schema_version: int = 1,
    graph: WorkflowGraph | None = None,
    graph_node: GraphNode | None = None,
    node_outputs: dict[str, dict[str, Any]] | None = None,
    input_ports: list[NodePort] | None = None,
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Facade used by the engine. Dispatches only on schema_version."""
    version = schema_version
    if graph is not None:
        version = graph_schema_version(graph)

    if version >= 2:
        if graph is None or graph_node is None:
            raise ValueError("schema_version >= 2 requires graph and graph_node")
        outputs = node_outputs or {}
        # When callers only pass upstream_outputs, rebuild a minimal node_outputs map.
        if not outputs and upstream_outputs and graph is not None:
            incoming = [e for e in graph.edges if e.target == graph_node.id]
            outputs = {
                edge.source: dict(upstream_outputs[idx])
                for idx, edge in enumerate(incoming)
                if idx < len(upstream_outputs)
            }
        return resolve_ports_and_bindings(
            graph=graph,
            graph_node=graph_node,
            trigger_payload=trigger_payload,
            initial_inputs=initial_inputs,
            node_outputs=outputs,
            input_ports=input_ports,
            run_context=run_context,
            run_id=run_id,
        )

    return resolve_legacy_node_inputs(
        node_type=node_type,
        trigger_payload=trigger_payload,
        initial_inputs=initial_inputs,
        upstream_outputs=upstream_outputs,
        run_id=run_id,
    )
