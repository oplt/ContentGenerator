"""Ready-node / unlock helpers for the workflow engine (Phase 4 control-flow)."""

from __future__ import annotations

from collections import defaultdict

from backend.modules.workflows.engine_node_index import NodeRunIndex
from backend.modules.workflows.graph_schema import GraphEdge, WorkflowGraph
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus

_SUCCESS = {
    WorkflowNodeRunStatus.SUCCEEDED.value,
    WorkflowNodeRunStatus.SKIPPED.value,
}
_OPEN = {
    WorkflowNodeRunStatus.PENDING.value,
    WorkflowNodeRunStatus.READY.value,
    WorkflowNodeRunStatus.QUEUED.value,
    WorkflowNodeRunStatus.RUNNING.value,
    WorkflowNodeRunStatus.WAITING.value,
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


def _pred_rows(
    edge: GraphEdge,
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
) -> list[WorkflowNodeRun]:
    if isinstance(node_runs, NodeRunIndex):
        return node_runs.iterations(edge.source)
    source = node_runs.get(edge.source)
    return [source] if source is not None else []


def _merge_mode(graph: WorkflowGraph, node_id: str) -> str | None:
    graph_node = next((n for n in graph.nodes if n.id == node_id), None)
    if graph_node is None or graph_node.type != "merge":
        return None
    return str((graph_node.config or {}).get("mode") or "all")


def _branch_satisfied(
    edge: GraphEdge,
    row: WorkflowNodeRun,
) -> bool:
    """SUCCEEDED satisfies; SKIPPED satisfies non-approval edges; approval needs SUCCEEDED."""
    if edge.condition == "approved":
        return row.status == WorkflowNodeRunStatus.SUCCEEDED.value
    return row.status in _SUCCESS


def is_ready(
    node_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
) -> bool:
    if isinstance(node_runs, NodeRunIndex):
        current = node_runs.get(node_id)
    else:
        current = node_runs.get(node_id)
    if current is None:
        return False
    if current.status not in {
        WorkflowNodeRunStatus.PENDING.value,
        WorkflowNodeRunStatus.READY.value,
        WorkflowNodeRunStatus.QUEUED.value,
    }:
        return False

    preds = predecessors(graph).get(node_id, [])
    if not preds:
        return True

    mode = _merge_mode(graph, node_id)
    if mode == "any":
        return _merge_any_ready(preds, node_runs)
    if mode == "all":
        return _merge_all_ready(preds, node_runs)

    # Non-merge: every predecessor branch must be satisfied (SUCCEEDED or SKIPPED).
    for edge in preds:
        rows = _pred_rows(edge, node_runs)
        if not rows:
            return False
        for row in rows:
            if not _branch_satisfied(edge, row):
                return False
    return True


def _merge_any_ready(
    preds: list[GraphEdge],
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
) -> bool:
    """Ready once any qualifying upstream SUCCEEDED — do not wait for siblings."""
    for edge in preds:
        for row in _pred_rows(edge, node_runs):
            if row.status != WorkflowNodeRunStatus.SUCCEEDED.value:
                continue
            return True
    return False


def _merge_all_ready(
    preds: list[GraphEdge],
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
) -> bool:
    """Ready when every incoming branch is satisfied; SKIPPED counts, FAILED does not."""
    for edge in preds:
        rows = _pred_rows(edge, node_runs)
        if not rows:
            return False
        for row in rows:
            if row.status in _OPEN:
                return False
            if not _branch_satisfied(edge, row):
                return False
    return True


def ready_node_ids(
    graph: WorkflowGraph,
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
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
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
) -> list[str]:
    from backend.modules.workflows.engine_unlock import unlock_downstream as _unlock

    return _unlock(source_id, graph=graph, node_runs=node_runs)


def run_is_waiting(node_runs: NodeRunIndex | dict[str, WorkflowNodeRun]) -> bool:
    rows = node_runs.values() if hasattr(node_runs, "values") else list(node_runs.values())
    return any(n.status == WorkflowNodeRunStatus.WAITING.value for n in rows)


def run_has_failure(node_runs: NodeRunIndex | dict[str, WorkflowNodeRun]) -> bool:
    rows = node_runs.values() if hasattr(node_runs, "values") else list(node_runs.values())
    return any(n.status == WorkflowNodeRunStatus.FAILED.value for n in rows)


def run_all_complete(node_runs: NodeRunIndex | dict[str, WorkflowNodeRun]) -> bool:
    rows = list(node_runs.values() if hasattr(node_runs, "values") else node_runs.values())
    return bool(rows) and all(n.status in _TERMINAL for n in rows)
