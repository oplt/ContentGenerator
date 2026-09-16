"""Controlled operator recovery: retry / resume (Phase 15).

Cancellation lives in ``workflow_cancellation`` (Phase 16).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from backend.modules.workflows.engine_ready import successors
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.workflow_cancellation import cancel_run

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine

__all__ = [
    "cancel_run",
    "retry_from_node",
    "retry_node",
    "resume_node",
]

_RETRYABLE_NODE = {WorkflowNodeRunStatus.FAILED.value}
_RESET_DESCENDANT = {
    WorkflowNodeRunStatus.PENDING.value,
    WorkflowNodeRunStatus.READY.value,
    WorkflowNodeRunStatus.QUEUED.value,
    WorkflowNodeRunStatus.RUNNING.value,
    WorkflowNodeRunStatus.WAITING.value,
    WorkflowNodeRunStatus.FAILED.value,
    WorkflowNodeRunStatus.SKIPPED.value,
    WorkflowNodeRunStatus.CANCELLED.value,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clear_claim(node: WorkflowNodeRun) -> None:
    node.claim_token = None
    node.claim_expires_at = None
    node.claimed_at = None
    node.worker_task_id = None
    node.last_heartbeat_at = None


def _reset_failed_to_ready(node: WorkflowNodeRun) -> None:
    """Prepare a FAILED node for another attempt; keep output for idempotent nodes."""
    if node.status == WorkflowNodeRunStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Cannot retry a succeeded node")
    if node.status not in _RETRYABLE_NODE:
        raise HTTPException(
            status_code=409,
            detail=f"Node '{node.node_id}' is {node.status}; only failed nodes can be retried",
        )
    _clear_claim(node)
    node.status = WorkflowNodeRunStatus.READY.value
    node.error_json = None
    node.last_error = None
    node.error_class = None
    node.waiting_reason = None
    node.finished_at = None
    node.next_attempt_at = None
    node.cancellation_requested = False


def _reset_descendant_to_pending(node: WorkflowNodeRun) -> None:
    if node.status == WorkflowNodeRunStatus.SUCCEEDED.value:
        return
    if node.status not in _RESET_DESCENDANT:
        return
    _clear_claim(node)
    node.status = WorkflowNodeRunStatus.PENDING.value
    node.error_json = None
    node.last_error = None
    node.error_class = None
    node.waiting_reason = None
    node.resume_token = None
    node.input_json = {}
    node.output_json = {}
    node.started_at = None
    node.finished_at = None
    node.next_attempt_at = None
    node.cancellation_requested = False


def _reopen_run(run: WorkflowRun) -> None:
    run.status = WorkflowRunStatus.RUNNING.value
    run.error_message = None
    run.finished_at = None


async def _load_graph(engine: WorkflowEngine, run: WorkflowRun) -> WorkflowGraph:
    version = await engine.versions.get_version(run.tenant_id, run.workflow_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    return WorkflowGraph.model_validate(version.graph_json)


async def retry_node(
    engine: WorkflowEngine,
    tenant_id: UUID,
    run_id: UUID,
    node_id: str,
    *,
    advance: bool = True,
) -> WorkflowRun:
    run = await engine.runs.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status == WorkflowRunStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Cannot retry a cancelled run")
    if run.status == WorkflowRunStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Cannot retry a succeeded run")

    nodes = await engine.runs.list_node_runs(tenant_id, run_id)
    target = next((n for n in nodes if n.node_id == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found on run")
    _reset_failed_to_ready(target)
    _reopen_run(run)
    await engine.db.flush()
    if advance:
        return await engine.advance(tenant_id, run_id)
    return run


async def retry_from_node(
    engine: WorkflowEngine,
    tenant_id: UUID,
    run_id: UUID,
    node_id: str,
    *,
    advance: bool = True,
) -> WorkflowRun:
    run = await engine.runs.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status == WorkflowRunStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Cannot retry a cancelled run")
    if run.status == WorkflowRunStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Cannot retry a succeeded run")

    graph = await _load_graph(engine, run)
    nodes = await engine.runs.list_node_runs(tenant_id, run_id)
    by_id = {n.node_id: n for n in nodes}
    target = by_id.get(node_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found on run")
    if target.status == WorkflowNodeRunStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Cannot retry from a succeeded node")
    if target.status != WorkflowNodeRunStatus.FAILED.value:
        raise HTTPException(
            status_code=409,
            detail=f"Node '{node_id}' is {target.status}; retry-from requires failed",
        )

    _reset_failed_to_ready(target)

    succ = successors(graph)
    queue: deque[str] = deque(edge.target for edge in succ.get(node_id, []))
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        row = by_id.get(current)
        if row is not None:
            _reset_descendant_to_pending(row)
        for edge in succ.get(current, []):
            queue.append(edge.target)

    _reopen_run(run)
    await engine.db.flush()
    if advance:
        return await engine.advance(tenant_id, run_id)
    return run


async def resume_node(
    engine: WorkflowEngine,
    tenant_id: UUID,
    run_id: UUID,
    node_id: str,
    *,
    outcome: str,
    decision: dict[str, object] | None = None,
    advance: bool = True,
) -> WorkflowRun:
    """Resume a WAITING node without exposing resume_token to the client."""
    from backend.modules.workflows.engine_resume import resume_waiting_node

    run = await engine.runs.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status == WorkflowRunStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="Cannot resume a cancelled run")
    nodes = await engine.runs.list_node_runs(tenant_id, run_id)
    target = next((n for n in nodes if n.node_id == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found on run")
    if target.status != WorkflowNodeRunStatus.WAITING.value or not target.resume_token:
        raise HTTPException(status_code=409, detail=f"Node '{node_id}' is not resumable")
    return await resume_waiting_node(
        engine,
        tenant_id,
        resume_token=target.resume_token,
        outcome=outcome,
        decision=decision,
        advance=advance,
    )
