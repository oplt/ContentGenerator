"""Ready-node / unlock helpers for the linear workflow engine."""

from __future__ import annotations

from collections import defaultdict

from backend.modules.workflows.graph_schema import GraphEdge, WorkflowGraph
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus

_SUCCESS = {
    WorkflowNodeRunStatus.SUCCEEDED.value,
    WorkflowNodeRunStatus.SKIPPED.value,
}
_TERMINAL = _SUCCESS | {
    WorkflowNodeRunStatus.FAILED.value,
    WorkflowNodeRunStatus.CANCELLED.value,
}


def predecessors(graph: WorkflowGraph) -> dict[str, list[GraphEdge]]:
    preds: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges:
        preds[edge.target].append(edge)
    return preds


def successors(graph: WorkflowGraph) -> dict[str, list[GraphEdge]]:
    succs: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges:
        succs[edge.source].append(edge)
    return succs


def root_node_ids(graph: WorkflowGraph) -> list[str]:
    targeted = {edge.target for edge in graph.edges}
    return [node.id for node in graph.nodes if node.id not in targeted]


def is_ready(
    node_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
) -> bool:
    current = node_runs[node_id]
    if current.status not in {
        WorkflowNodeRunStatus.PENDING.value,
        WorkflowNodeRunStatus.READY.value,
        WorkflowNodeRunStatus.QUEUED.value,
    }:
        return False

    preds = predecessors(graph).get(node_id, [])
    if not preds:
        return True

    graph_node = next((n for n in graph.nodes if n.id == node_id), None)
    merge_any = (
        graph_node is not None
        and graph_node.type == "merge"
        and str((graph_node.config or {}).get("mode") or "all") == "any"
    )

    succeeded = 0
    for edge in preds:
        source = node_runs.get(edge.source)
        if source is None:
            return False
        if source.status not in _SUCCESS:
            return False
        if edge.condition == "approved" and source.status != WorkflowNodeRunStatus.SUCCEEDED.value:
            return False
        if source.status == WorkflowNodeRunStatus.SUCCEEDED.value:
            succeeded += 1

    if merge_any:
        return succeeded >= 1
    return True


def ready_node_ids(
    graph: WorkflowGraph, node_runs: dict[str, WorkflowNodeRun]
) -> list[str]:
    return [
        node.id
        for node in graph.nodes
        if node.id in node_runs and is_ready(node.id, graph=graph, node_runs=node_runs)
    ]


def unlock_downstream(
    source_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
) -> list[str]:
    from backend.modules.workflows.engine_unlock import unlock_downstream as _unlock

    return _unlock(source_id, graph=graph, node_runs=node_runs)


def run_is_waiting(node_runs: dict[str, WorkflowNodeRun]) -> bool:
    return any(n.status == WorkflowNodeRunStatus.WAITING.value for n in node_runs.values())


def run_has_failure(node_runs: dict[str, WorkflowNodeRun]) -> bool:
    return any(n.status == WorkflowNodeRunStatus.FAILED.value for n in node_runs.values())


def run_all_complete(node_runs: dict[str, WorkflowNodeRun]) -> bool:
    return bool(node_runs) and all(n.status in _TERMINAL for n in node_runs.values())
