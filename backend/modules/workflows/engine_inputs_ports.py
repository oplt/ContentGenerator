"""Port/binding input resolver (schema_version >= 2).

Engine-facing resolution with no node-type switches. Uses edges, ports, bindings,
and generic name-fill from the upstream bag.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.modules.workflows.engine_inputs_bag import lookup_dotted, merge_upstream_bag
from backend.modules.workflows.graph_schema import GraphEdge, GraphNode, InputBinding, WorkflowGraph
from backend.modules.workflows.nodes.base import NodePort


def _incoming_edges(graph: WorkflowGraph, node_id: str) -> list[GraphEdge]:
    return [edge for edge in graph.edges if edge.target == node_id]


def _resolve_binding(
    binding: InputBinding,
    *,
    trigger_payload: dict[str, Any],
    initial_inputs: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    run_context: dict[str, Any],
) -> Any:
    source = binding.source
    if source == "constant":
        return binding.value
    if source == "trigger":
        if binding.path:
            return lookup_dotted(trigger_payload, binding.path)
        return dict(trigger_payload)
    if source == "workflow_input":
        if binding.path:
            return lookup_dotted(initial_inputs, binding.path)
        return dict(initial_inputs)
    if source == "context":
        return lookup_dotted(run_context, binding.path) if binding.path else dict(run_context)
    if source == "node":
        node_id = binding.node_id
        if not node_id:
            return None
        output = node_outputs.get(node_id) or {}
        path = binding.path or binding.port
        return lookup_dotted(output, path) if path else dict(output)
    return None


def _apply_edge(
    inputs: dict[str, Any],
    *,
    edge: GraphEdge,
    source_output: dict[str, Any],
    port_types: dict[str, str],
) -> None:
    sport = edge.source_port
    tport = edge.target_port
    if sport and tport:
        if sport in source_output:
            value = source_output[sport]
        else:
            value = None
        _assign_port(inputs, tport, value, port_types)
        return
    if tport and not sport:
        # Whole upstream output into one port (object) or collect for arrays.
        _assign_port(inputs, tport, dict(source_output), port_types)
        return
    if sport and not tport:
        if sport in source_output:
            inputs[sport] = source_output[sport]
        return
    # No ports: merge upstream keys into the working bag/inputs (non-destructive).
    for key, value in source_output.items():
        inputs.setdefault(key, value)


def _assign_port(
    inputs: dict[str, Any],
    port_name: str,
    value: Any,
    port_types: dict[str, str],
) -> None:
    if port_types.get(port_name) == "array":
        existing = inputs.get(port_name)
        if existing is None:
            inputs[port_name] = [value] if not isinstance(value, list) else list(value)
        elif isinstance(existing, list):
            if isinstance(value, list):
                existing.extend(value)
            else:
                existing.append(value)
        else:
            inputs[port_name] = value
        return
    inputs[port_name] = value


def resolve_ports_and_bindings(
    *,
    graph: WorkflowGraph,
    graph_node: GraphNode,
    trigger_payload: dict[str, Any],
    initial_inputs: dict[str, Any],
    node_outputs: dict[str, dict[str, Any]],
    input_ports: list[NodePort] | None = None,
    run_context: dict[str, Any] | None = None,
    run_id: UUID | None = None,
) -> dict[str, Any]:
    """Resolve inputs from bindings + edge ports + generic name-fill."""
    _ = run_id  # reserved for future binding helpers; idempotency injected later
    run_context = dict(run_context or {})
    ports = list(input_ports or [])
    port_types = {p.name: p.data_type for p in ports}
    port_names = {p.name for p in ports}

    incoming = _incoming_edges(graph, graph_node.id)
    upstream_outputs = [
        dict(node_outputs.get(edge.source) or {}) for edge in incoming
    ]
    bag = merge_upstream_bag(
        trigger_payload=trigger_payload,
        initial_inputs=initial_inputs,
        upstream_outputs=upstream_outputs,
    )

    inputs: dict[str, Any] = {}
    bound_keys = set((graph_node.input_bindings or {}).keys())

    # 1) Explicit bindings (highest priority for declared ports).
    for target_port, binding in (graph_node.input_bindings or {}).items():
        if isinstance(binding, dict):
            binding = InputBinding.model_validate(binding)
        inputs[target_port] = _resolve_binding(
            binding,
            trigger_payload=trigger_payload,
            initial_inputs=initial_inputs,
            node_outputs=node_outputs,
            run_context=run_context,
        )

    # 2) Edge port mappings (do not override explicit bindings).
    for edge in incoming:
        if edge.target_port and edge.target_port in bound_keys:
            continue
        source_output = dict(node_outputs.get(edge.source) or {})
        _apply_edge(
            inputs,
            edge=edge,
            source_output=source_output,
            port_types=port_types,
        )

    # 3) Generic name-fill from bag for declared ports still missing.
    for port in ports:
        if port.name in inputs:
            continue
        if port.name in bag:
            inputs[port.name] = bag[port.name]
        elif port.name == "payload" and not incoming:
            inputs[port.name] = dict(trigger_payload or initial_inputs or {})
        elif port.name == "bag":
            inputs[port.name] = dict(bag)
        elif port.data_type == "array" and upstream_outputs and port.name == "sources":
            inputs[port.name] = [dict(o) for o in upstream_outputs if isinstance(o, dict)]

    # 4) If node declares no ports, expose the merged bag (trigger adapters, etc.).
    if not port_names:
        merged = dict(bag)
        merged.update(inputs)
        return merged

    return inputs
