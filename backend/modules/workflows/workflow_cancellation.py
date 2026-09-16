"""End-to-end workflow cancellation (Phase 16).

Cancellation is durable state management — not history deletion.
SUCCEEDED nodes (and their side effects, e.g. published posts) stay recorded.
Active Celery work is revoked only with terminate=False (safe).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import update

from backend.modules.operations.models import TaskExecution
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
    WorkflowWaitStatus,
)

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine

# Phase 16 primary targets; FAILED/QUEUED kept for operator recovery UX.
_CANCELABLE_RUN = {
    WorkflowRunStatus.QUEUED.value,
    WorkflowRunStatus.RUNNING.value,
    WorkflowRunStatus.WAITING.value,
    WorkflowRunStatus.FAILED.value,
}

_IMMEDIATE_CANCEL_NODE = {
    WorkflowNodeRunStatus.PENDING.value,
    WorkflowNodeRunStatus.READY.value,
    WorkflowNodeRunStatus.WAITING.value,
    WorkflowNodeRunStatus.FAILED.value,
}

_ACTIVE_NODE = {
    WorkflowNodeRunStatus.QUEUED.value,
    WorkflowNodeRunStatus.RUNNING.value,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clear_claim(node: WorkflowNodeRun) -> None:
    node.claim_token = None
    node.claim_expires_at = None
    node.claimed_at = None
    node.worker_task_id = None
    node.last_heartbeat_at = None


def _mark_node_cancelled(node: WorkflowNodeRun, *, now: datetime, reason: str) -> None:
    _clear_claim(node)
    node.status = WorkflowNodeRunStatus.CANCELLED.value
    node.finished_at = now
    node.waiting_reason = None
    node.next_attempt_at = None
    node.cancellation_requested = True
    if not node.error_json:
        node.error_json = {"code": "cancelled", "message": reason}


def request_celery_cancel(celery_task_id: str | None) -> bool:
    """Ask Celery not to run / continue a task. Never uses terminate=True."""
    if not celery_task_id or celery_task_id in {"inline", "local"}:
        return False
    try:
        from backend.workers.celery_app import celery_app

        celery_app.control.revoke(celery_task_id, terminate=False)
        return True
    except Exception:  # noqa: BLE001 — broker optional in tests / offline
        return False


async def _flag_task_execution(
    engine: WorkflowEngine, *, task_execution_id: UUID | None, now: datetime
) -> None:
    if task_execution_id is None:
        return
    te = await engine.db.get(TaskExecution, task_execution_id)
    if te is None:
        return
    te.cancellation_requested = True
    if te.cancelled_at is None:
        te.cancelled_at = now


async def _cancel_pending_waits(
    engine: WorkflowEngine, *, tenant_id: UUID, run_id: UUID, now: datetime
) -> None:
    await engine.db.execute(
        update(WorkflowWait)
        .where(
            WorkflowWait.tenant_id == tenant_id,
            WorkflowWait.workflow_run_id == run_id,
            WorkflowWait.status == WorkflowWaitStatus.PENDING.value,
        )
        .values(
            status=WorkflowWaitStatus.CANCELLED.value,
            resolved_at=now,
            resolved_outcome="cancelled",
        )
    )


async def cancel_run(
    engine: WorkflowEngine,
    tenant_id: UUID,
    run_id: UUID,
) -> WorkflowRun:
    run = await engine.runs.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status == WorkflowRunStatus.SUCCEEDED.value:
        raise HTTPException(status_code=409, detail="Cannot cancel a succeeded run")
    if run.status == WorkflowRunStatus.CANCELLED.value:
        return run
    if run.status not in _CANCELABLE_RUN:
        raise HTTPException(
            status_code=409, detail=f"Run status '{run.status}' cannot be cancelled"
        )

    now = _now()
    reason = "cancelled by operator"
    nodes = await engine.runs.list_node_runs(tenant_id, run_id)

    for node in nodes:
        if node.status == WorkflowNodeRunStatus.SUCCEEDED.value:
            # Irreversible / completed work stays recorded.
            continue
        if node.status == WorkflowNodeRunStatus.CANCELLED.value:
            node.cancellation_requested = True
            continue
        if node.status in _IMMEDIATE_CANCEL_NODE:
            _mark_node_cancelled(node, now=now, reason=reason)
            await _flag_task_execution(engine, task_execution_id=node.task_execution_id, now=now)
            continue
        if node.status in _ACTIVE_NODE:
            node.cancellation_requested = True
            await _flag_task_execution(engine, task_execution_id=node.task_execution_id, now=now)
            request_celery_cancel(node.worker_task_id)
            # Durable cancel: mark CANCELLED. Worker that already produced SUCCEEDED
            # will keep SUCCEEDED (see execute_claimed_node_run race guard).
            _mark_node_cancelled(node, now=now, reason=reason)

    await _cancel_pending_waits(engine, tenant_id=tenant_id, run_id=run_id, now=now)
    run.status = WorkflowRunStatus.CANCELLED.value
    run.finished_at = now
    run.error_message = run.error_message or reason

    from backend.modules.workflows.occurrence_sync import sync_occurrence_for_run

    await sync_occurrence_for_run(engine.db, run)
    await engine.db.flush()
    return run


def should_abort_node(node: WorkflowNodeRun, run: WorkflowRun) -> bool:
    """True when a worker must stop before / instead of domain execution."""
    if run.status == WorkflowRunStatus.CANCELLED.value:
        return True
    return bool(node.cancellation_requested)


async def abort_node_for_cancellation(
    engine: WorkflowEngine,
    *,
    tenant_id: UUID,
    node: WorkflowNodeRun,
    claim_token: str | None,
    reason: str = "cancelled",
) -> None:
    now = _now()
    node.cancellation_requested = True
    if node.status != WorkflowNodeRunStatus.SUCCEEDED.value:
        _mark_node_cancelled(node, now=now, reason=reason)
    await _flag_task_execution(engine, task_execution_id=node.task_execution_id, now=now)
    from backend.modules.workflows import run_repository as node_claims

    await node_claims.complete_node(
        engine.db,
        tenant_id=tenant_id,
        node_run_id=node.id,
        claim_token=claim_token,
    )
