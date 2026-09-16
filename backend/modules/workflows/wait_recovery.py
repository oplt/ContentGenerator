"""Wake due WorkflowWait rows and continue workflow runs (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.wait_store import claim_due_waits


async def wake_due_workflow_waits(
    db: AsyncSession,
    *,
    batch_size: int = 50,
    enqueue_resume: bool = True,
) -> list[dict[str, Any]]:
    """Resolve due waits atomically, then resume waiting nodes.

    When ``enqueue_resume`` is False (inline tests), resume in-process.
    """
    claimed = await claim_due_waits(db, batch_size=batch_size)
    results: list[dict[str, Any]] = []
    for wait in claimed:
        outcome = str(wait.resolved_outcome or "elapsed")
        decision: dict[str, Any] = {}
        payload = dict(wait.payload or {}) if isinstance(wait.payload, dict) else {}
        if outcome == "expired":
            on_timeout = payload.get("on_timeout") or wait.timeout_action
            if on_timeout == "fail":
                on_timeout = "stop"
            if on_timeout:
                decision["on_timeout"] = on_timeout
            await _expire_bound_approval_request(db, payload)
        results.append(
            {
                "wait_id": str(wait.id),
                "tenant_id": str(wait.tenant_id),
                "workflow_run_id": str(wait.workflow_run_id),
                "resume_token": wait.resume_token,
                "outcome": outcome,
            }
        )
        from backend.modules.workflows.observability import record_workflow_wait_resolved

        record_workflow_wait_resolved(
            wait_type=str(wait.wait_type or "delay"),
            outcome=outcome,
            created_at=wait.created_at,
            resolved_at=datetime.now(timezone.utc),
            tenant_id=wait.tenant_id,
            workflow_run_id=wait.workflow_run_id,
            resume_token=wait.resume_token,
        )
        if enqueue_resume:
            _enqueue_resume(
                tenant_id=wait.tenant_id,
                resume_token=wait.resume_token,
                outcome=outcome,
                decision=decision,
            )
        else:
            from backend.modules.workflows.engine import WorkflowEngine
            from backend.modules.workflows.engine_resume import resume_waiting_node

            await resume_waiting_node(
                WorkflowEngine(db),
                wait.tenant_id,
                resume_token=wait.resume_token,
                outcome=outcome,
                decision=decision,
                advance=True,
            )
    await db.flush()
    return results


async def _expire_bound_approval_request(
    db: AsyncSession, payload: dict[str, Any]
) -> None:
    """Mark the linked ApprovalRequest expired when durable approval wait times out."""
    if payload.get("kind") != "approval_timeout":
        return
    raw_id = payload.get("approval_request_id")
    if not raw_id:
        return
    try:
        request_id = UUID(str(raw_id))
    except (TypeError, ValueError):
        return
    from backend.modules.approvals.models import ApprovalRequest, ApprovalStatus

    request = await db.get(ApprovalRequest, request_id)
    if request is None:
        return
    if request.status == ApprovalStatus.PENDING.value:
        request.status = ApprovalStatus.EXPIRED.value


def _enqueue_resume(
    *,
    tenant_id: UUID,
    resume_token: str,
    outcome: str,
    decision: dict[str, Any],
) -> None:
    try:
        from backend.workers.tasks import resume_workflow_waiting_node_task
    except Exception:  # noqa: BLE001
        return
    resume_workflow_waiting_node_task.delay(
        tenant_id=str(tenant_id),
        resume_token=resume_token,
        outcome=outcome,
        decision=decision,
    )
