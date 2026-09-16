"""Workflow webhook ingress: inbox + idempotent run start (Phase 17)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.security import resolve_secret_reference
from backend.modules.approvals.models import WebhookInbox
from backend.modules.approvals.repository import ApprovalRepository
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.models import Automation, AutomationTriggerType
from backend.modules.workflows.security import sanitize_mapping
from backend.modules.workflows.webhook_crypto import (
    parse_timestamp,
    sanitize_trigger_payload,
    stable_event_id,
    verify_generic_hmac,
)
from backend.modules.workflows.webhook_trigger_config import parse_webhook_trigger_config


async def get_automation_by_endpoint(
    db: AsyncSession, endpoint_id: str
) -> Automation | None:
    result = await db.execute(
        select(Automation).where(
            Automation.webhook_endpoint_id == endpoint_id,
            Automation.deleted_at.is_(None),
            Automation.trigger_type.in_(
                [
                    AutomationTriggerType.WEBHOOK.value,
                    AutomationTriggerType.EVENT.value,
                ]
            ),
        )
    )
    return result.scalar_one_or_none()


async def _reserve_replay(key: str, ttl_seconds: int) -> bool:
    """Return True if this is the first time seeing the key (NX)."""
    try:
        ok = await redis_client.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(ok)
    except Exception:  # noqa: BLE001 — Redis optional in some unit tests
        return True


async def receive_workflow_webhook(
    db: AsyncSession,
    *,
    endpoint_id: str,
    raw_body: bytes,
    headers: dict[str, str],
    process_inline: bool = False,
) -> dict[str, Any]:
    automation = await get_automation_by_endpoint(db, endpoint_id)
    if automation is None or not automation.enabled:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    try:
        cfg = parse_webhook_trigger_config(dict(automation.trigger_config or {}))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Invalid webhook config: {exc}") from exc

    secret = resolve_secret_reference(cfg.signing_secret_ref)
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook signing secret not configured")

    def _hdr(name: str) -> str | None:
        lowered = {k.lower(): v for k, v in headers.items()}
        return lowered.get(name.lower())

    signature_header = _hdr(cfg.signature_header)
    timestamp_header = _hdr(cfg.timestamp_header)
    idempotency_header = _hdr(cfg.idempotency_header)

    timestamp = parse_timestamp(timestamp_header)
    valid = verify_generic_hmac(
        secret=secret,
        body=raw_body,
        signature_header=signature_header,
        timestamp=timestamp,
        max_skew_seconds=cfg.max_skew_seconds,
        require_timestamp=cfg.require_timestamp,
    )
    if not valid:
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    event_id = stable_event_id(idempotency_key=idempotency_header, body=raw_body)
    replay_key = f"wf_webhook_replay:{endpoint_id}:{event_id}"
    if not await _reserve_replay(replay_key, ttl_seconds=max(cfg.max_skew_seconds * 2, 120)):
        # Replay — still idempotent via inbox
        pass

    dedupe_key = f"wf:{automation.tenant_id}:{endpoint_id}:{event_id}"
    repo = ApprovalRepository(db)
    existing = await repo.get_webhook_by_dedupe_key(dedupe_key)
    if existing is not None:
        return {
            "inbox_id": str(existing.id),
            "workflow_run_id": (existing.payload or {}).get("workflow_run_id"),
            "deduped": True,
            "status": existing.status,
        }

    try:
        parsed = json.loads(raw_body.decode("utf-8"))
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}
    except Exception:
        parsed = {"raw_text": raw_body.decode("utf-8", errors="ignore")}

    sanitized = sanitize_trigger_payload(parsed)
    try:
        inbox = await repo.create_webhook(
            WebhookInbox(
                tenant_id=automation.tenant_id,
                provider="workflow_webhook",
                event_type=f"automation:{automation.id}",
                dedupe_key=dedupe_key,
                payload={
                    "automation_id": str(automation.id),
                    "endpoint_id": endpoint_id,
                    "event_id": event_id,
                    "body_json": json.dumps(sanitized, default=str),
                },
                received_at=datetime.now(timezone.utc),
                signature_valid=True,
                status="received",
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await repo.get_webhook_by_dedupe_key(dedupe_key)
        if existing is None:
            raise
        return {
            "inbox_id": str(existing.id),
            "workflow_run_id": (existing.payload or {}).get("workflow_run_id"),
            "deduped": True,
            "status": existing.status,
        }

    if process_inline:
        result = await process_workflow_webhook_inbox(db, inbox_id=inbox.id)
        return {
            "inbox_id": str(inbox.id),
            "workflow_run_id": result.get("workflow_run_id"),
            "deduped": False,
            "status": result.get("status", "processed"),
        }

    from backend.workers.tasks import process_workflow_webhook_inbox_task

    process_workflow_webhook_inbox_task.delay(inbox_id=str(inbox.id))
    return {
        "inbox_id": str(inbox.id),
        "workflow_run_id": None,
        "deduped": False,
        "status": "received",
    }


async def process_workflow_webhook_inbox(
    db: AsyncSession, *, inbox_id: UUID
) -> dict[str, Any]:
    repo = ApprovalRepository(db)
    inbox = await repo.get_pending_webhook(inbox_id)
    if inbox is None:
        return {"status": "missing"}
    if inbox.status == "processed":
        return {
            "status": "processed",
            "workflow_run_id": (inbox.payload or {}).get("workflow_run_id"),
        }
    if inbox.status not in {"received", "error"}:
        return {"status": inbox.status}

    automation_id_raw = (inbox.payload or {}).get("automation_id")
    if not automation_id_raw:
        inbox.status = "error"
        inbox.error_message = "missing automation_id"
        await db.commit()
        return {"status": "error"}

    automation = await db.get(Automation, UUID(str(automation_id_raw)))
    if automation is None or not automation.enabled:
        inbox.status = "error"
        inbox.error_message = "automation unavailable"
        await db.commit()
        return {"status": "error"}

    body_json = (inbox.payload or {}).get("body_json") or "{}"
    try:
        trigger_payload = sanitize_mapping(json.loads(body_json))
    except Exception:
        trigger_payload = {}

    event_id = str((inbox.payload or {}).get("event_id") or inbox.dedupe_key)
    # Keep under WorkflowRun.correlation_id String(128).
    correlation_id = f"wh:{automation.id}:{event_id}"[:128]
    inbox.status = "processing"
    await db.flush()

    engine = WorkflowEngine(db)
    run = await engine.start_run(
        tenant_id=automation.tenant_id,
        workflow_version_id=automation.workflow_version_id,
        trigger_payload=trigger_payload,
        initial_inputs={"payload": trigger_payload},
        automation_id=automation.id,
        brand_id=automation.brand_id,
        correlation_id=correlation_id,
        trigger_type="webhook",
        advance=True,
    )
    payload = dict(inbox.payload or {})
    payload["workflow_run_id"] = str(run.id)
    inbox.payload = payload
    inbox.status = "processed"
    inbox.processed_at = datetime.now(timezone.utc)
    automation.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "processed", "workflow_run_id": str(run.id)}
