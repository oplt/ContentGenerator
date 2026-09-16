"""Atomic WorkflowNodeRun claim lease operations (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clear_claim_values() -> dict[str, object]:
    return {
        "claim_token": None,
        "claim_expires_at": None,
        "claimed_at": None,
        "worker_task_id": None,
        "last_heartbeat_at": None,
    }


def build_execution_key(
    *,
    workflow_run_id: UUID,
    node_id: str,
    node_version: int,
    iteration_key: str | None = None,
) -> str:
    base = f"{workflow_run_id}:{node_id}:v{node_version}"
    if iteration_key:
        return f"{base}:{iteration_key}"
    return base


async def claim_ready_node(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    workflow_run_id: UUID,
    node_run_id: UUID | None = None,
    lease_seconds: int | None = None,
) -> WorkflowNodeRun | None:
    """Atomically claim one READY node (FOR UPDATE SKIP LOCKED + conditional UPDATE)."""
    now = _now()
    lease = lease_seconds or settings.WORKFLOW_CLAIM_LEASE_SECONDS
    claim_expires_at = now + timedelta(seconds=lease)
    claim_token = uuid.uuid4().hex
    due = or_(
        WorkflowNodeRun.next_attempt_at.is_(None),
        WorkflowNodeRun.next_attempt_at <= now,
    )
    filters = [
        WorkflowNodeRun.tenant_id == tenant_id,
        WorkflowNodeRun.workflow_run_id == workflow_run_id,
        WorkflowNodeRun.status == WorkflowNodeRunStatus.READY.value,
        due,
    ]
    if node_run_id is not None:
        filters.append(WorkflowNodeRun.id == node_run_id)

    picked = await db.execute(
        select(WorkflowNodeRun.id)
        .where(*filters)
        .order_by(WorkflowNodeRun.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    row_id = picked.scalar_one_or_none()
    if row_id is None:
        return None

    claimed = await db.execute(
        update(WorkflowNodeRun)
        .where(
            WorkflowNodeRun.id == row_id,
            WorkflowNodeRun.status == WorkflowNodeRunStatus.READY.value,
            due,
        )
        .values(
            status=WorkflowNodeRunStatus.QUEUED.value,
            claim_token=claim_token,
            claim_expires_at=claim_expires_at,
            claimed_at=now,
            last_heartbeat_at=now,
            next_attempt_at=None,
        )
        .returning(WorkflowNodeRun)
    )
    node = claimed.scalar_one_or_none()
    if node is None:
        return None
    node.execution_key = build_execution_key(
        workflow_run_id=node.workflow_run_id,
        node_id=node.node_id,
        node_version=int(node.node_version or 1),
        iteration_key=node.iteration_key or None,
    )
    await db.flush()
    return node


async def renew_node_claim(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node_run_id: UUID,
    claim_token: str,
    lease_seconds: int | None = None,
    worker_task_id: str | None = None,
) -> WorkflowNodeRun | None:
    now = _now()
    lease = lease_seconds or settings.WORKFLOW_CLAIM_LEASE_SECONDS
    values: dict[str, object] = {
        "claim_expires_at": now + timedelta(seconds=lease),
        "last_heartbeat_at": now,
    }
    if worker_task_id is not None:
        values["worker_task_id"] = worker_task_id
    result = await db.execute(
        update(WorkflowNodeRun)
        .where(
            WorkflowNodeRun.tenant_id == tenant_id,
            WorkflowNodeRun.id == node_run_id,
            WorkflowNodeRun.claim_token == claim_token,
            WorkflowNodeRun.status.in_(
                [WorkflowNodeRunStatus.QUEUED.value, WorkflowNodeRunStatus.RUNNING.value]
            ),
        )
        .values(**values)
        .returning(WorkflowNodeRun)
    )
    node = result.scalar_one_or_none()
    if node is not None:
        await db.flush()
    return node


async def release_node_claim(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node_run_id: UUID,
    claim_token: str | None = None,
    requeue: bool = True,
    next_attempt_at: datetime | None = None,
) -> WorkflowNodeRun | None:
    filters = [
        WorkflowNodeRun.tenant_id == tenant_id,
        WorkflowNodeRun.id == node_run_id,
    ]
    if claim_token is not None:
        filters.append(WorkflowNodeRun.claim_token == claim_token)
    values = _clear_claim_values()
    if requeue:
        values["status"] = WorkflowNodeRunStatus.READY.value
        values["next_attempt_at"] = next_attempt_at
    result = await db.execute(
        update(WorkflowNodeRun).where(*filters).values(**values).returning(WorkflowNodeRun)
    )
    node = result.scalar_one_or_none()
    if node is not None:
        await db.flush()
    return node


async def complete_node(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node_run_id: UUID,
    claim_token: str | None = None,
) -> WorkflowNodeRun | None:
    filters = [
        WorkflowNodeRun.tenant_id == tenant_id,
        WorkflowNodeRun.id == node_run_id,
    ]
    if claim_token is not None:
        filters.append(WorkflowNodeRun.claim_token == claim_token)
    result = await db.execute(
        update(WorkflowNodeRun)
        .where(*filters)
        .values(**_clear_claim_values())
        .returning(WorkflowNodeRun)
    )
    node = result.scalar_one_or_none()
    if node is not None:
        await db.flush()
    return node


async def fail_node(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node_run_id: UUID,
    error: dict[str, object],
    claim_token: str | None = None,
    error_class: str | None = None,
    last_error: str | None = None,
) -> WorkflowNodeRun | None:
    now = _now()
    filters = [
        WorkflowNodeRun.tenant_id == tenant_id,
        WorkflowNodeRun.id == node_run_id,
    ]
    if claim_token is not None:
        filters.append(WorkflowNodeRun.claim_token == claim_token)
    message = last_error or str(error.get("message") or error.get("code") or "node failed")
    values = {
        **_clear_claim_values(),
        "status": WorkflowNodeRunStatus.FAILED.value,
        "error_json": error,
        "finished_at": now,
        "next_attempt_at": None,
        "last_error": message if len(message) <= 2000 else message[:2000],
        "error_class": error_class or str(error.get("error_class") or "permanent"),
    }
    result = await db.execute(
        update(WorkflowNodeRun).where(*filters).values(**values).returning(WorkflowNodeRun)
    )
    node = result.scalar_one_or_none()
    if node is not None:
        await db.flush()
    return node


async def begin_node_execution(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    node_run_id: UUID,
    claim_token: str,
    worker_task_id: str | None,
    task_execution_id: UUID | None,
    lease_seconds: int | None = None,
) -> WorkflowNodeRun | None:
    now = _now()
    lease = lease_seconds or settings.WORKFLOW_CLAIM_LEASE_SECONDS
    node = await db.get(WorkflowNodeRun, node_run_id)
    if node is None or node.tenant_id != tenant_id or node.claim_token != claim_token:
        return None
    if node.cancellation_requested:
        return None
    if node.status not in {
        WorkflowNodeRunStatus.QUEUED.value,
        WorkflowNodeRunStatus.RUNNING.value,
    }:
        return None
    node.status = WorkflowNodeRunStatus.RUNNING.value
    node.claim_expires_at = now + timedelta(seconds=lease)
    node.last_heartbeat_at = now
    if worker_task_id:
        node.worker_task_id = worker_task_id
    if task_execution_id is not None:
        node.task_execution_id = task_execution_id
        existing = list(node.task_execution_ids or [])
        te_str = str(task_execution_id)
        if te_str not in existing:
            existing.append(te_str)
            node.task_execution_ids = existing
    await db.flush()
    return node


async def list_stale_claimed_nodes(
    db: AsyncSession,
    *,
    batch_size: int | None = None,
) -> list[WorkflowNodeRun]:
    now = _now()
    size = batch_size or settings.WORKFLOW_CLAIM_RECOVERY_BATCH_SIZE
    result = await db.execute(
        select(WorkflowNodeRun)
        .where(
            WorkflowNodeRun.status.in_(
                [WorkflowNodeRunStatus.QUEUED.value, WorkflowNodeRunStatus.RUNNING.value]
            ),
            WorkflowNodeRun.claim_expires_at.is_not(None),
            WorkflowNodeRun.claim_expires_at <= now,
        )
        .order_by(WorkflowNodeRun.claim_expires_at.asc())
        .limit(size)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())
