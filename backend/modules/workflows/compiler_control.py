"""Compile-time rules for control-flow nodes (Phase 12)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.modules.workflows.compiler_types import WorkflowCompileError
from backend.modules.workflows.graph_schema import GraphEdge, WorkflowGraph
from backend.modules.workflows.nodes.base import WorkflowNode


def validate_control_flow(
    graph: WorkflowGraph,
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
) -> list[WorkflowCompileError]:
    errors: list[WorkflowCompileError] = []
    outgoing: dict[str, list[GraphEdge]] = defaultdict(list)
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)

    for node_id, node in resolved.items():
        if node.type == "condition":
            errors.extend(_condition_errors(node_id, node, outgoing.get(node_id, [])))
        elif node.type == "merge":
            n_in = len(incoming.get(node_id, []))
            if n_in < 1:
                errors.append(
                    WorkflowCompileError(
                        code="merge_requires_inputs",
                        message=f"merge '{node_id}' requires at least one incoming edge",
                        node_id=node_id,
                        node_type="merge",
                    )
                )
        elif node.type == "fan_out":
            outs = outgoing.get(node_id, [])
            if len(outs) != 1:
                errors.append(
                    WorkflowCompileError(
                        code="fan_out_single_successor",
                        message=(
                            f"fan_out '{node_id}' must have exactly one outgoing edge "
                            "(spawns one WorkflowNodeRun per item on that successor)"
                        ),
                        node_id=node_id,
                        node_type="fan_out",
                    )
                )
            elif outs[0].condition is not None:
                errors.append(
                    WorkflowCompileError(
                        code="fan_out_unconditional_edge",
                        message=f"fan_out '{node_id}' outgoing edge must be unconditional",
                        node_id=node_id,
                        node_type="fan_out",
                    )
                )
    return errors


def _condition_errors(
    node_id: str,
    node: WorkflowNode[Any, Any, Any],
    outs: list[GraphEdge],
) -> list[WorkflowCompileError]:
    errors: list[WorkflowCompileError] = []
    if len(outs) < 2:
        errors.append(
            WorkflowCompileError(
                code="condition_requires_branches",
                message=f"condition '{node_id}' requires at least two outgoing edges",
                node_id=node_id,
                node_type="condition",
            )
        )
        return errors
    labels = [e.condition for e in outs]
    if any(label is None or not str(label).strip() for label in labels):
        errors.append(
            WorkflowCompileError(
                code="condition_edge_labels_required",
                message=f"condition '{node_id}' outgoing edges must each set condition labels",
                node_id=node_id,
                node_type="condition",
            )
        )
    stripped = [str(label).strip() for label in labels if label]
    if len(stripped) != len(set(stripped)):
        errors.append(
            WorkflowCompileError(
                code="condition_duplicate_labels",
                message=f"condition '{node_id}' has duplicate edge condition labels",
                node_id=node_id,
                node_type="condition",
            )
        )
    return errors
