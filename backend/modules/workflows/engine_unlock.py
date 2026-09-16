"""Unlock / skip cascade for branched workflow graphs (Phase 12)."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from backend.modules.workflows.engine_ready import is_ready, predecessors, successors
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus

_SKIPPABLE = {
    WorkflowNodeRunStatus.PENDING.value,
    WorkflowNodeRunStatus.READY.value,
    WorkflowNodeRunStatus.QUEUED.value,
}


def unlock_downstream(
    source_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
) -> list[str]:
    """Legacy helper — unconditional unlock of ready pending successors."""
    return unlock_after_node_success(
        source_id, graph=graph, node_runs=node_runs, output=None
    )


def unlock_after_node_success(
    source_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
    output: dict[str, object] | None = None,
) -> list[str]:
    """Unlock successors; when source emits ``branch``, skip non-matching conditional edges."""
    outs = successors(graph).get(source_id, [])
    branch = None
    if isinstance(output, dict):
        raw = output.get("branch")
        if isinstance(raw, str) and raw.strip():
            branch = raw.strip()

    has_conditional = any(edge.condition for edge in outs)
    unlocked: list[str] = []

    if has_conditional and branch is not None:
        for edge in outs:
            target = node_runs.get(edge.target)
            if target is None:
                continue
            if edge.condition is None or edge.condition == branch:
                if target.status == WorkflowNodeRunStatus.PENDING.value and is_ready(
                    edge.target, graph=graph, node_runs=node_runs
                ):
                    target.status = WorkflowNodeRunStatus.READY.value
                    unlocked.append(edge.target)
            elif edge.condition is not None:
                cascade_skip(edge.target, graph=graph, node_runs=node_runs)
        return unlocked

    for edge in outs:
        target = node_runs.get(edge.target)
        if target is None:
            continue
        if target.status != WorkflowNodeRunStatus.PENDING.value:
            continue
        if is_ready(edge.target, graph=graph, node_runs=node_runs):
            target.status = WorkflowNodeRunStatus.READY.value
            unlocked.append(edge.target)
    return unlocked


def cascade_skip(
    node_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
) -> list[str]:
    """Mark node SKIPPED and cascade to descendants whose every predecessor is SKIPPED."""
    skipped: list[str] = []
    queue: deque[str] = deque([node_id])
    now = datetime.now(timezone.utc)
    while queue:
        current_id = queue.popleft()
        current = node_runs.get(current_id)
        if current is None or current.status not in _SKIPPABLE:
            continue
        current.status = WorkflowNodeRunStatus.SKIPPED.value
        current.finished_at = now
        current.waiting_reason = None
        current.error_json = None
        skipped.append(current_id)
        for edge in successors(graph).get(current_id, []):
            if _all_preds_skipped(edge.target, graph=graph, node_runs=node_runs):
                queue.append(edge.target)
    return skipped


def _all_preds_skipped(
    node_id: str,
    *,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
) -> bool:
    preds = predecessors(graph).get(node_id, [])
    if not preds:
        return False
    for edge in preds:
        source = node_runs.get(edge.source)
        if source is None or source.status != WorkflowNodeRunStatus.SKIPPED.value:
            return False
    return True
