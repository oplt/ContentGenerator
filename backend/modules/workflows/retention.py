"""Phase 20 — retain workflow/ops history without unbounded JSON growth.

Policy:
* Scrub terminal ``WorkflowNodeRun`` input/output JSON after age threshold.
* Delete finished ``TaskExecution`` rows after age threshold.
* Clear processed webhook inbox payloads after age threshold (keep receipt row).
* Never delete ``audit_logs``.
* Optional S3/MinIO archive before scrub when configured.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics
from backend.modules.approvals.models import WebhookInbox
from backend.modules.operations.models import TaskExecution
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus

logger = logging.getLogger(__name__)

_TERMINAL_NODE_STATUSES = (
    WorkflowNodeRunStatus.SUCCEEDED.value,
    WorkflowNodeRunStatus.FAILED.value,
    WorkflowNodeRunStatus.CANCELLED.value,
    WorkflowNodeRunStatus.SKIPPED.value,
)

_FINISHED_TASK_STATUSES = ("completed", "failed", "cancelled", "revoked")

_WEBHOOK_DONE_STATUSES = ("processed", "error", "duplicate")

_SCRUB_MARKER = "_retention"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_already_scrubbed(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    marker = payload.get(_SCRUB_MARKER)
    return isinstance(marker, dict) and marker.get("scrubbed") is True


def _scrub_stub(*, archived_object_key: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        _SCRUB_MARKER: {
            "scrubbed": True,
            "scrubbed_at": _utc_now().isoformat(),
            "reason": "age_policy",
        }
    }
    if archived_object_key:
        cast_marker = body[_SCRUB_MARKER]
        assert isinstance(cast_marker, dict)
        cast_marker["archive_object_key"] = archived_object_key
    return body


async def _maybe_archive_payload(
    *,
    kind: str,
    tenant_id: UUID | None,
    entity_id: UUID,
    payload: Mapping[str, object],
) -> str | None:
    if not settings.WORKFLOW_RETENTION_ARCHIVE_TO_STORAGE:
        return None
    if not payload or _is_already_scrubbed(payload):
        return None
    from backend.core.storage import StorageNotConfiguredError, object_storage

    if not object_storage.is_configured:
        return None
    tenant_part = str(tenant_id) if tenant_id else "unknown"
    object_key = (
        f"retention/{kind}/tenants/{tenant_part}/{entity_id}.json"
    )
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    try:
        await object_storage.upload_bytes(
            object_key=object_key,
            body=body,
            content_type="application/json",
        )
    except StorageNotConfiguredError:
        return None
    except Exception as exc:  # noqa: BLE001 — archive is best-effort
        logger.warning(
            "retention_archive_failed kind=%s entity_id=%s error=%s",
            kind,
            entity_id,
            exc,
        )
        return None
    return object_key


async def scrub_old_node_payloads(
    db: AsyncSession,
    *,
    older_than: datetime,
    batch_size: int,
) -> int:
    """Replace large node I/O JSON with a scrub stub for terminal finished nodes."""
    result = await db.execute(
        select(WorkflowNodeRun)
        .where(
            WorkflowNodeRun.status.in_(_TERMINAL_NODE_STATUSES),
            WorkflowNodeRun.finished_at.is_not(None),
            WorkflowNodeRun.finished_at < older_than,
        )
        .order_by(WorkflowNodeRun.finished_at.asc())
        .limit(batch_size * 3)
    )
    nodes = list(result.scalars().all())
    scrubbed = 0
    for node in nodes:
        if scrubbed >= batch_size:
            break
        if _is_already_scrubbed(node.input_json) and _is_already_scrubbed(node.output_json):
            continue
        has_live_input = bool(node.input_json) and not _is_already_scrubbed(node.input_json)
        has_live_output = bool(node.output_json) and not _is_already_scrubbed(node.output_json)
        if not has_live_input and not has_live_output:
            continue

        archive_key: str | None = None
        combined: dict[str, object] = {}
        if has_live_input:
            combined["input_json"] = dict(node.input_json)
        if has_live_output:
            combined["output_json"] = dict(node.output_json)
        archive_key = await _maybe_archive_payload(
            kind="workflow_node_run",
            tenant_id=node.tenant_id,
            entity_id=node.id,
            payload=combined,
        )

        stub = _scrub_stub(archived_object_key=archive_key)
        if has_live_input or not _is_already_scrubbed(node.input_json):
            node.input_json = stub
        if has_live_output or not _is_already_scrubbed(node.output_json):
            node.output_json = stub
        scrubbed += 1
    if scrubbed:
        await db.flush()
    return scrubbed


async def delete_old_task_executions(
    db: AsyncSession,
    *,
    older_than: datetime,
    batch_size: int,
) -> int:
    """Hard-delete finished TaskExecution telemetry rows past retention."""
    candidates = await db.execute(
        select(TaskExecution.id)
        .where(
            TaskExecution.status.in_(_FINISHED_TASK_STATUSES),
            or_(
                and_(
                    TaskExecution.finished_at.is_not(None),
                    TaskExecution.finished_at < older_than,
                ),
                and_(
                    TaskExecution.finished_at.is_(None),
                    TaskExecution.created_at < older_than,
                ),
            ),
        )
        .order_by(TaskExecution.created_at.asc())
        .limit(batch_size)
    )
    ids = list(candidates.scalars().all())
    if not ids:
        return 0
    await db.execute(delete(TaskExecution).where(TaskExecution.id.in_(ids)))
    await db.flush()
    return len(ids)


async def scrub_old_webhook_payloads(
    db: AsyncSession,
    *,
    older_than: datetime,
    batch_size: int,
) -> int:
    """Clear large webhook bodies; keep inbox rows for receipt / dedupe."""
    result = await db.execute(
        select(WebhookInbox)
        .where(
            WebhookInbox.status.in_(_WEBHOOK_DONE_STATUSES),
            WebhookInbox.received_at.is_not(None),
            WebhookInbox.received_at < older_than,
        )
        .order_by(WebhookInbox.received_at.asc())
        .limit(batch_size * 2)
    )
    rows = list(result.scalars().all())
    scrubbed = 0
    for inbox in rows:
        if scrubbed >= batch_size:
            break
        if _is_already_scrubbed(inbox.payload):
            continue
        if not inbox.payload:
            inbox.payload = _scrub_stub()  # type: ignore[assignment]
            scrubbed += 1
            continue
        payload = dict(inbox.payload or {})
        archive_key = await _maybe_archive_payload(
            kind="webhook_inbox",
            tenant_id=inbox.tenant_id,
            entity_id=inbox.id,
            payload=payload,
        )
        inbox.payload = _scrub_stub(archived_object_key=archive_key)  # type: ignore[assignment]
        scrubbed += 1
    if scrubbed:
        await db.flush()
    return scrubbed


async def run_workflow_retention(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Apply configured retention policies once (one batch per category)."""
    started = time.perf_counter()
    if not settings.WORKFLOW_RETENTION_ENABLED:
        return {
            "enabled": False,
            "nodes_scrubbed": 0,
            "task_executions_deleted": 0,
            "webhooks_scrubbed": 0,
        }

    clock = now or _utc_now()
    size = batch_size if batch_size is not None else settings.WORKFLOW_RETENTION_BATCH_SIZE
    node_cutoff = clock - timedelta(days=settings.WORKFLOW_RETENTION_NODE_PAYLOAD_DAYS)
    task_cutoff = clock - timedelta(days=settings.WORKFLOW_RETENTION_TASK_EXECUTION_DAYS)
    webhook_cutoff = clock - timedelta(days=settings.WORKFLOW_RETENTION_WEBHOOK_PAYLOAD_DAYS)

    nodes_scrubbed = await scrub_old_node_payloads(
        db, older_than=node_cutoff, batch_size=size
    )
    tasks_deleted = await delete_old_task_executions(
        db, older_than=task_cutoff, batch_size=size
    )
    webhooks_scrubbed = await scrub_old_webhook_payloads(
        db, older_than=webhook_cutoff, batch_size=size
    )
    await db.flush()

    duration_ms = (time.perf_counter() - started) * 1000.0
    domain_metrics.record_operation(
        "workflow.retention",
        outcome="success",
        duration_ms=duration_ms,
    )
    summary = {
        "enabled": True,
        "nodes_scrubbed": nodes_scrubbed,
        "task_executions_deleted": tasks_deleted,
        "webhooks_scrubbed": webhooks_scrubbed,
        "node_cutoff": node_cutoff.isoformat(),
        "task_cutoff": task_cutoff.isoformat(),
        "webhook_cutoff": webhook_cutoff.isoformat(),
    }
    logger.info(
        "workflow_retention_complete nodes=%s tasks=%s webhooks=%s duration_ms=%.1f",
        nodes_scrubbed,
        tasks_deleted,
        webhooks_scrubbed,
        duration_ms,
    )
    return summary
