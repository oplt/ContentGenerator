"""Create durable WorkflowWait rows when delay/wait nodes enter WAITING (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowWaitType,
)
from backend.modules.workflows.wait_store import create_wait, schedule_fast_wake


def _parse_resume_at(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        resume_at = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            resume_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if resume_at.tzinfo is None:
        resume_at = resume_at.replace(tzinfo=timezone.utc)
    return resume_at


async def persist_waiting_node(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    node_run: WorkflowNodeRun,
    output: dict[str, Any],
    waiting_reason: str | None,
) -> None:
    """Persist Postgres-owned wait row; optionally enqueue Celery fast wake."""
    token = node_run.resume_token
    if not token:
        return

    now = datetime.now(timezone.utc)
    if node_run.node_type == "delay" or waiting_reason == "delay_until":
        resume_at = _parse_resume_at(output.get("resume_at")) or (now + timedelta(seconds=1))
        await create_wait(
            db,
            tenant_id=run.tenant_id,
            workflow_run_id=run.id,
            workflow_node_run_id=node_run.id,
            resume_token=token,
            wait_type=WorkflowWaitType.DELAY.value,
            wake_at=resume_at,
            payload={"resume_at": resume_at.isoformat()},
        )
        schedule_fast_wake(
            tenant_id=run.tenant_id,
            resume_token=token,
            wake_at=resume_at,
            outcome="elapsed",
        )
        return

    if node_run.node_type == "wait" or waiting_reason == "event_pending":
        timeout_seconds = output.get("timeout_seconds")
        wake_at: datetime | None = None
        timeout_action: str | None = None
        if isinstance(timeout_seconds, int) and timeout_seconds > 0:
            wake_at = now + timedelta(seconds=timeout_seconds)
            timeout_action = str(output.get("on_timeout") or "fail")
        event_key = output.get("correlation_key")
        if event_key is not None:
            event_key = str(event_key).strip() or None
        await create_wait(
            db,
            tenant_id=run.tenant_id,
            workflow_run_id=run.id,
            workflow_node_run_id=node_run.id,
            resume_token=token,
            wait_type=WorkflowWaitType.EVENT.value,
            wake_at=wake_at,
            event_key=event_key,
            timeout_action=timeout_action,
            payload={
                "event": output.get("event"),
                "correlation_key": event_key,
            },
        )
        if wake_at is not None:
            schedule_fast_wake(
                tenant_id=run.tenant_id,
                resume_token=token,
                wake_at=wake_at,
                outcome="expired",
                decision={"on_timeout": timeout_action or "fail"},
            )
        return

    if node_run.node_type == "approval" or waiting_reason == "approval_pending":
        timeout_seconds = output.get("timeout_seconds")
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            timeout_seconds = 86_400
        on_timeout = str(output.get("on_timeout") or "stop")
        wake_at = now + timedelta(seconds=timeout_seconds)
        approval_request_id = output.get("approval_request_id")
        event_key = (
            f"approval:{approval_request_id}" if approval_request_id else None
        )
        await create_wait(
            db,
            tenant_id=run.tenant_id,
            workflow_run_id=run.id,
            workflow_node_run_id=node_run.id,
            resume_token=token,
            wait_type=WorkflowWaitType.EVENT.value,
            wake_at=wake_at,
            event_key=event_key,
            timeout_action="continue" if on_timeout == "continue" else "fail",
            payload={
                "kind": "approval_timeout",
                "approval_request_id": approval_request_id,
                "on_timeout": on_timeout,
            },
        )
        schedule_fast_wake(
            tenant_id=run.tenant_id,
            resume_token=token,
            wake_at=wake_at,
            outcome="expired",
            decision={"on_timeout": on_timeout},
        )
