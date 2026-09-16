"""DAG structural checks for the workflow compiler."""

from __future__ import annotations

from collections import defaultdict, deque

from typing import Any

from backend.modules.workflows.compiler_types import WorkflowCompileError
from backend.modules.workflows.graph_schema import GraphEdge, GraphNode, WorkflowGraph
from backend.modules.workflows.nodes.base import NodePort, WorkflowNode


def find_duplicate_node_ids(nodes: list[GraphNode]) -> list[WorkflowCompileError]:
    seen: set[str] = set()
    errors: list[WorkflowCompileError] = []
    for node in nodes:
        if node.id in seen:
            errors.append(
                WorkflowCompileError(
                    code="duplicate_node_id",
                    message=f"duplicate node id '{node.id}'",
                    node_id=node.id,
                    node_type=node.type,
                )
            )
        else:
            seen.add(node.id)
    return errors


def validate_edges(
    graph: WorkflowGraph, node_ids: set[str]
) -> list[WorkflowCompileError]:
    errors: list[WorkflowCompileError] = []
    for edge in graph.edges:
        if edge.source not in node_ids:
            errors.append(
                WorkflowCompileError(
                    code="dangling_edge_source",
                    message=f"edge source '{edge.source}' does not exist",
                    node_id=edge.source,
                )
            )
        if edge.target not in node_ids:
            errors.append(
                WorkflowCompileError(
                    code="dangling_edge_target",
                    message=f"edge target '{edge.target}' does not exist",
                    node_id=edge.target,
                )
            )
        if edge.source and edge.target and edge.source == edge.target:
            errors.append(
                WorkflowCompileError(
                    code="self_edge",
                    message=f"edge cannot connect node '{edge.source}' to itself",
                    node_id=edge.source,
                )
            )
    return errors


def detect_cycles(node_ids: set[str], edges: list[GraphEdge]) -> list[WorkflowCompileError]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.source in node_ids and edge.target in node_ids:
            adjacency[edge.source].append(edge.target)

    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[WorkflowCompileError] = []

    def _dfs(node_id: str, stack: list[str]) -> None:
        if node_id in visiting:
            cycle = " -> ".join([*stack[stack.index(node_id) :], node_id])
            errors.append(
                WorkflowCompileError(
                    code="cycle_detected",
                    message=f"workflow graph contains a cycle: {cycle}",
                    node_id=node_id,
                )
            )
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        stack.append(node_id)
        for nxt in adjacency.get(node_id, []):
            _dfs(nxt, stack)
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(node_ids):
        if node_id not in visited:
            _dfs(node_id, [])
    return errors


def find_unreachable(
    node_ids: set[str], edges: list[GraphEdge], roots: set[str]
) -> list[WorkflowCompileError]:
    if not node_ids:
        return []
    if not roots:
        return [
            WorkflowCompileError(
                code="unreachable_nodes",
                message="no trigger/root nodes; all nodes are unreachable",
            )
        ]

    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.source in node_ids and edge.target in node_ids:
            adjacency[edge.source].append(edge.target)

    seen: set[str] = set()
    queue: deque[str] = deque(sorted(roots))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for nxt in adjacency.get(current, []):
            if nxt not in seen:
                queue.append(nxt)

    errors: list[WorkflowCompileError] = []
    for node_id in sorted(node_ids - seen):
        errors.append(
            WorkflowCompileError(
                code="unreachable_node",
                message=f"node '{node_id}' is unreachable from trigger roots",
                node_id=node_id,
            )
        )
    return errors


def types_compatible(source_type: str, target_type: str) -> bool:
    src = source_type.strip().lower()
    dst = target_type.strip().lower()
    if src in {"any", "object"} or dst in {"any", "object"}:
        return True
    if src == dst:
        return True
    aliases = {
        "str": "string",
        "text": "string",
        "int": "number",
        "float": "number",
        "bool": "boolean",
        "list": "array",
    }
    src = aliases.get(src, src)
    dst = aliases.get(dst, dst)
    if src == dst:
        return True
    # Soft coercions used by content pipelines.
    if {src, dst} <= {"string", "uuid"}:
        return True
    if src == "array" and dst.startswith("array"):
        return True
    return False


def validate_port_compatibility(
    edges: list[GraphEdge],
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
) -> list[WorkflowCompileError]:
    errors: list[WorkflowCompileError] = []
    for edge in edges:
        source = resolved.get(edge.source)
        target = resolved.get(edge.target)
        if source is None or target is None:
            continue
        out_ports = list(source.output_ports)
        in_ports = list(target.input_ports)
        if not out_ports or not in_ports:
            continue

        if edge.source_port:
            out_ports = [p for p in out_ports if p.name == edge.source_port]
            if not out_ports:
                errors.append(
                    WorkflowCompileError(
                        code="unknown_source_port",
                        message=f"source port '{edge.source_port}' not on '{edge.source}'",
                        node_id=edge.source,
                        node_type=source.type,
                    )
                )
                continue
        if edge.target_port:
            in_ports = [p for p in in_ports if p.name == edge.target_port]
            if not in_ports:
                errors.append(
                    WorkflowCompileError(
                        code="unknown_target_port",
                        message=f"target port '{edge.target_port}' not on '{edge.target}'",
                        node_id=edge.target,
                        node_type=target.type,
                    )
                )
                continue

        required_inputs = [p for p in in_ports if p.required] or in_ports
        if not _any_compatible(out_ports, required_inputs):
            errors.append(
                WorkflowCompileError(
                    code="incompatible_ports",
                    message=(
                        f"no compatible port types from '{edge.source}' "
                        f"({source.type}) to '{edge.target}' ({target.type})"
                    ),
                    node_id=edge.target,
                    node_type=target.type,
                )
            )
    return errors


def _any_compatible(outputs: list[NodePort], inputs: list[NodePort]) -> bool:
    return any(
        types_compatible(out.data_type, inp.data_type) for out in outputs for inp in inputs
    )


def validate_input_bindings(
    graph: WorkflowGraph,
    resolved: dict[str, WorkflowNode[Any, Any, Any]],
) -> list[WorkflowCompileError]:
    """Validate declarative input_bindings (enforced for all versions when present)."""
    errors: list[WorkflowCompileError] = []
    node_ids = {node.id for node in graph.nodes}
    for node in graph.nodes:
        impl = resolved.get(node.id)
        port_names = {p.name for p in (impl.input_ports if impl else [])}
        for target_port, binding in (node.input_bindings or {}).items():
            if port_names and target_port not in port_names:
                errors.append(
                    WorkflowCompileError(
                        code="unknown_binding_target",
                        message=(
                            f"input binding target '{target_port}' is not an input port "
                            f"on '{node.id}'"
                        ),
                        node_id=node.id,
                        node_type=node.type,
                    )
                )
            if binding.source == "node":
                if not binding.node_id:
                    errors.append(
                        WorkflowCompileError(
                            code="invalid_binding",
                            message=f"binding '{target_port}' missing node_id",
                            node_id=node.id,
                            node_type=node.type,
                        )
                    )
                elif binding.node_id not in node_ids:
                    errors.append(
                        WorkflowCompileError(
                            code="invalid_binding",
                            message=(
                                f"binding '{target_port}' references unknown node "
                                f"'{binding.node_id}'"
                            ),
                            node_id=node.id,
                            node_type=node.type,
                        )
                    )
            if binding.source == "constant" and binding.value is None and not binding.path:
                errors.append(
                    WorkflowCompileError(
                        code="invalid_binding",
                        message=f"constant binding '{target_port}' requires value",
                        node_id=node.id,
                        node_type=node.type,
                    )
                )
    return errors
