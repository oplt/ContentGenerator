"""Run-status finalization helpers for the linear workflow engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.modules.workflows.engine_ready import (
    run_all_complete,
    run_has_failure,
    run_is_waiting,
)
from backend.modules.workflows.engine_node_index import NodeRunIndex
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)


def as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _rows(node_runs: NodeRunIndex | dict[str, WorkflowNodeRun]) -> list[WorkflowNodeRun]:
    if isinstance(node_runs, NodeRunIndex):
        return list(node_runs.rows)
    return list(node_runs.values())


def finalize_run_status(
    run: WorkflowRun, node_runs: NodeRunIndex | dict[str, WorkflowNodeRun]
) -> None:
    now = datetime.now(timezone.utc)
    # Operator cancel is sticky — do not reopen from node finalization.
    if run.status == WorkflowRunStatus.CANCELLED.value:
        if run.finished_at is None:
            run.finished_at = now
        return
    if run_has_failure(node_runs):
        run.status = WorkflowRunStatus.FAILED.value
        failed = next(
            n for n in _rows(node_runs) if n.status == WorkflowNodeRunStatus.FAILED.value
        )
        run.error_message = str((failed.error_json or {}).get("message") or "node failed")
        run.finished_at = now
    elif run_is_waiting(node_runs):
        run.status = WorkflowRunStatus.WAITING.value
        run.finished_at = None
    elif run_all_complete(node_runs):
        if any(n.status == WorkflowNodeRunStatus.CANCELLED.value for n in _rows(node_runs)):
            run.status = WorkflowRunStatus.CANCELLED.value
            run.finished_at = now
            run.error_message = run.error_message or "cancelled"
        else:
            run.status = WorkflowRunStatus.SUCCEEDED.value
            run.finished_at = now
            run.error_message = None
    else:
        run.status = WorkflowRunStatus.RUNNING.value
        return
    if run.finished_at is not None:
        from backend.modules.workflows.observability import record_workflow_run_finished

        record_workflow_run_finished(run)
