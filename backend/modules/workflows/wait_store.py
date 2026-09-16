"""Persist and claim durable WorkflowWait rows (Phase 5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.run_models import (
    WorkflowWait,
    WorkflowWaitStatus,
    WorkflowWaitType,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_wait(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    workflow_run_id: UUID,
    workflow_node_run_id: UUID,
    resume_token: str,
    wait_type: str,
    wake_at: datetime | None = None,
    event_key: str | None = None,
    timeout_action: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkflowWait:
    row = WorkflowWait(
        tenant_id=tenant_id,
        workflow_run_id=workflow_run_id,
        workflow_node_run_id=workflow_node_run_id,
        resume_token=resume_token,
        wait_type=wait_type,
        wake_at=wake_at,
        event_key=event_key,
        timeout_action=timeout_action,
        payload=dict(payload or {}),
        status=WorkflowWaitStatus.PENDING.value,
    )
    db.add(row)
    await db.flush()
    return row


async def get_pending_by_resume_token(
    db: AsyncSession, *, resume_token: str
) -> WorkflowWait | None:
    result = await db.execute(
        select(WorkflowWait).where(
            WorkflowWait.resume_token == resume_token,
            WorkflowWait.status == WorkflowWaitStatus.PENDING.value,
        )
    )
    return result.scalar_one_or_none()


async def get_pending_by_event_key(
    db: AsyncSession, *, tenant_id: UUID, event_key: str
) -> WorkflowWait | None:
    result = await db.execute(
        select(WorkflowWait).where(
            WorkflowWait.tenant_id == tenant_id,
            WorkflowWait.event_key == event_key,
            WorkflowWait.status == WorkflowWaitStatus.PENDING.value,
        )
    )
    return result.scalar_one_or_none()


async def mark_wait_resolved(
    db: AsyncSession,
    *,
    wait_id: UUID,
    outcome: str,
    payload_update: dict[str, Any] | None = None,
) -> WorkflowWait | None:
    """Atomically resolve a pending wait. Returns None if already resolved."""
    now = _now()
    values: dict[str, object] = {
        "status": WorkflowWaitStatus.RESOLVED.value,
        "resolved_at": now,
        "resolved_outcome": outcome,
    }
    if payload_update:
        # Load then merge — keep claim simple and portable across dialects.
        current = await db.get(WorkflowWait, wait_id)
        if current is None or current.status != WorkflowWaitStatus.PENDING.value:
            return None
        merged = dict(current.payload or {})
        merged.update(payload_update)
        values["payload"] = merged

    result = await db.execute(
        update(WorkflowWait)
        .where(
            WorkflowWait.id == wait_id,
            WorkflowWait.status == WorkflowWaitStatus.PENDING.value,
        )
        .values(**values)
        .returning(WorkflowWait)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await db.flush()
    return row


async def mark_wait_resolved_by_resume_token(
    db: AsyncSession,
    *,
    resume_token: str,
    outcome: str,
    payload_update: dict[str, Any] | None = None,
) -> WorkflowWait | None:
    pending = await get_pending_by_resume_token(db, resume_token=resume_token)
    if pending is None:
        return None
    return await mark_wait_resolved(
        db, wait_id=pending.id, outcome=outcome, payload_update=payload_update
    )


async def resolve_wait_by_event_key(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    event_key: str,
    payload: dict[str, Any] | None = None,
) -> WorkflowWait | None:
    """Atomically resolve a pending event wait by provider correlation key."""
    pending = await get_pending_by_event_key(db, tenant_id=tenant_id, event_key=event_key)
    if pending is None:
        return None
    return await mark_wait_resolved(
        db,
        wait_id=pending.id,
        outcome="received",
        payload_update={"event_payload": dict(payload or {})},
    )


async def claim_due_waits(
    db: AsyncSession,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
) -> list[WorkflowWait]:
    """Claim pending waits whose wake_at is due (FOR UPDATE SKIP LOCKED)."""
    now = now or _now()
    picked = await db.execute(
        select(WorkflowWait.id)
        .where(
            WorkflowWait.status == WorkflowWaitStatus.PENDING.value,
            WorkflowWait.wake_at.is_not(None),
            WorkflowWait.wake_at <= now,
        )
        .order_by(WorkflowWait.wake_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    ids = list(picked.scalars().all())
    if not ids:
        return []

    claimed: list[WorkflowWait] = []
    for wait_id in ids:
        row = await db.get(WorkflowWait, wait_id)
        if row is None or row.status != WorkflowWaitStatus.PENDING.value:
            continue
        outcome = "elapsed" if row.wait_type == WorkflowWaitType.DELAY.value else "expired"
        resolved = await mark_wait_resolved(db, wait_id=row.id, outcome=outcome)
        if resolved is not None:
            claimed.append(resolved)
    return claimed


def schedule_fast_wake(
    *,
    tenant_id: UUID,
    resume_token: str,
    wake_at: datetime,
    outcome: str,
    decision: dict[str, Any] | None = None,
) -> None:
    """Best-effort Celery countdown. Postgres wake_at remains authoritative."""
    now = _now()
    if wake_at.tzinfo is None:
        wake_at = wake_at.replace(tzinfo=timezone.utc)
    countdown = max(0, int((wake_at - now).total_seconds()))
    try:
        from backend.workers.tasks import resume_workflow_waiting_node_task
    except Exception:  # noqa: BLE001 — unit tests may lack Celery wiring
        return
    resume_workflow_waiting_node_task.apply_async(
        kwargs={
            "tenant_id": str(tenant_id),
            "resume_token": resume_token,
            "outcome": outcome,
            "decision": decision or {},
        },
        countdown=countdown,
    )
