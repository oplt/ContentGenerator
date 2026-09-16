"""Resume WAITING workflow nodes (approvals + control-flow pauses)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from backend.modules.workflows.engine_status import as_dict, finalize_run_status
from backend.modules.workflows.engine_unlock import unlock_after_node_success
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine

_APPROVED = "approved"
_REJECTED = "rejected"
_EXPIRED = "expired"
_ELAPSED = "elapsed"
_RECEIVED = "received"
_SUCCESS_OUTCOMES = {_APPROVED, _ELAPSED, _RECEIVED}
_FAIL_OUTCOMES = {_REJECTED, _EXPIRED}
_VALID_OUTCOMES = _SUCCESS_OUTCOMES | _FAIL_OUTCOMES


async def resume_waiting_node(
    engine: WorkflowEngine,
    tenant_id: UUID,
    *,
    resume_token: str | None = None,
    outcome: str,
    decision: dict[str, Any] | None = None,
    advance: bool = True,
) -> WorkflowRun:
    """Mark WAITING node SUCCEEDED/FAILED from an external decision, then advance.

    Never re-executes the paused node. Worker is not held during the wait.
    """
    normalized = outcome.strip().lower()
    if normalized not in _VALID_OUTCOMES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported resume outcome '{outcome}'",
        )
    if not resume_token:
        raise HTTPException(status_code=422, detail="resume_token is required")

    node_run = await engine.runs.get_by_resume_token(tenant_id, resume_token)
    if node_run is None:
        raise HTTPException(status_code=404, detail="Waiting node not found for resume token")

    run = await engine.runs.get_run(tenant_id, node_run.workflow_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    # Idempotent: already resolved successfully.
    if node_run.status == WorkflowNodeRunStatus.SUCCEEDED.value and normalized in _SUCCESS_OUTCOMES:
        if advance and run.status in {
            WorkflowRunStatus.QUEUED.value,
            WorkflowRunStatus.RUNNING.value,
            WorkflowRunStatus.WAITING.value,
        }:
            return await engine.advance(tenant_id, run.id)
        return run
    if node_run.status == WorkflowNodeRunStatus.FAILED.value and normalized in _FAIL_OUTCOMES:
        return run
    if node_run.status != WorkflowNodeRunStatus.WAITING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Node is not waiting (status={node_run.status})",
        )

    version = await engine.versions.get_version(tenant_id, run.workflow_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    graph = WorkflowGraph.model_validate(version.graph_json)
    node_runs = await engine._node_map(tenant_id, run.id)
    snapshot = as_dict(run.context_snapshot)
    node_outputs: dict[str, Any] = as_dict(snapshot.get("node_outputs"))
    now = datetime.now(timezone.utc)
    decision_payload = dict(decision or {})
    on_timeout = str(decision_payload.get("on_timeout") or "stop")

    output = dict(node_run.output_json or {})
    output.update(decision_payload)
    output["decision"] = normalized
    output["status"] = normalized

    if normalized in {_APPROVED, _ELAPSED, _RECEIVED}:
        node_run.status = WorkflowNodeRunStatus.SUCCEEDED.value
        node_run.output_json = output
        node_run.error_json = None
        node_run.finished_at = now
        node_run.waiting_reason = None
        node_outputs[node_run.node_id] = output
        unlock_after_node_success(
            node_run.node_id, graph=graph, node_runs=node_runs, output=output
        )
        run.status = WorkflowRunStatus.RUNNING.value
        wait_outcome = normalized
    elif normalized == _EXPIRED and on_timeout == "continue":
        output["status"] = "timed_out"
        node_run.status = WorkflowNodeRunStatus.SUCCEEDED.value
        node_run.output_json = output
        node_run.error_json = None
        node_run.finished_at = now
        node_run.waiting_reason = None
        node_outputs[node_run.node_id] = output
        unlock_after_node_success(
            node_run.node_id, graph=graph, node_runs=node_runs, output=output
        )
        run.status = WorkflowRunStatus.RUNNING.value
        wait_outcome = "expired_continue"
    else:
        code_prefix = "approval" if node_run.node_type == "approval" else "wait"
        node_run.status = WorkflowNodeRunStatus.FAILED.value
        node_run.output_json = output
        node_run.error_json = {
            "code": f"{code_prefix}_{normalized}",
            "message": f"Wait/approval {normalized}",
        }
        node_run.finished_at = now
        node_run.waiting_reason = None
        node_outputs[node_run.node_id] = output
        wait_outcome = normalized

    if node_run.node_type == "approval":
        from backend.modules.workflows.observability import record_approval_wait

        record_approval_wait(run, node_run, outcome=wait_outcome)

    snapshot["node_outputs"] = node_outputs
    run.context_snapshot = snapshot
    finalize_run_status(run, node_runs)
    await engine.db.flush()

    if advance and run.status == WorkflowRunStatus.RUNNING.value:
        return await engine.advance(tenant_id, run.id)
    return run


def node_run_lookup_hint(node_run: WorkflowNodeRun) -> dict[str, Any]:
    return {
        "workflow_run_id": str(node_run.workflow_run_id),
        "node_id": node_run.node_id,
        "resume_token": node_run.resume_token,
    }
