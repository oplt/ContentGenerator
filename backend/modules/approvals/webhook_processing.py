from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals.models import ApprovalMessage, ApprovalRequest, WebhookInbox
from backend.modules.approvals.providers import get_whatsapp_provider
from backend.modules.approvals.providers import WhatsAppRuntimeConfig


class _WebhookDeps(Protocol):
    db: AsyncSession
    repo: Any
    settings_service: Any
    audit: Any

    def _extract_phone_number_id(self, payload: dict[str, Any]) -> str | None: ...
    async def _apply_intent(self, request: ApprovalRequest, intent: str, feedback: str | None) -> None: ...


async def handle_webhook(
    svc,
    *,
    payload: dict[str, Any],
    raw_body: bytes,
    signature: str | None,
) -> str:
    """
    Fast path: verify signature, write to WebhookInbox, return immediately.
    The actual intent processing is done asynchronously by process_webhook_inbox_task.
    """
    tenant_phone_number_id = svc._extract_phone_number_id(payload)
    resolved_tenant_id: UUID | None = None
    runtime_config: WhatsAppRuntimeConfig | None = None
    if tenant_phone_number_id:
        resolved_tenant_id = await svc.settings_service.find_tenant_id_by_whatsapp_phone_number_id(
            tenant_phone_number_id
        )
        if resolved_tenant_id:
            runtime_config = await svc.settings_service.resolve_whatsapp_runtime_config(
                resolved_tenant_id
            )
    if runtime_config is None:
        runtime_config = svc.settings_service._global_whatsapp_runtime_config()
    provider = get_whatsapp_provider(runtime_config)

    signature_valid = provider.verify_signature(body=raw_body, signature=signature)
    if not signature_valid and runtime_config.app_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    dedupe_key = hashlib.sha256(raw_body).hexdigest()
    existing_webhook = await svc.repo.get_webhook_by_dedupe_key(dedupe_key)
    if existing_webhook:
        return str(existing_webhook.id)  # Idempotent

    inbox = await svc.repo.create_webhook(
        WebhookInbox(
            tenant_id=resolved_tenant_id,
            provider=runtime_config.provider,
            event_type="incoming_message",
            dedupe_key=dedupe_key,
            payload={"raw": raw_body.decode("utf-8", errors="ignore")},
            received_at=datetime.now(timezone.utc),
            signature_valid=signature_valid,
            status="received",
        )
    )
    await svc.db.commit()
    return str(inbox.id)


async def process_webhook_inbox(svc, inbox_id: UUID) -> list[ApprovalRequest]:
    """
    Called by Celery. Processes a single WebhookInbox row: parses intent and acts.
    """
    inbox = await svc.repo.get_pending_webhook(inbox_id)
    if not inbox or inbox.status != "received":
        return []

    raw_payload_str = inbox.payload.get("raw", "")
    import json as _json
    try:
        payload = _json.loads(raw_payload_str)
    except Exception:
        inbox.status = "error"
        inbox.error_message = "JSON parse failed"
        await svc.db.commit()
        return []

    runtime_config: WhatsAppRuntimeConfig | None = None
    if inbox.tenant_id:
        runtime_config = await svc.settings_service.resolve_whatsapp_runtime_config(inbox.tenant_id)
    if runtime_config is None:
        runtime_config = svc.settings_service._global_whatsapp_runtime_config()
    provider = get_whatsapp_provider(runtime_config)

    inbox.status = "processing"
    await svc.db.flush()

    updated_requests: list[ApprovalRequest] = []
    try:
        for parsed in provider.parse_payload(payload):
            request_id = parsed.approval_request_id
            if request_id is None:
                text_parts = (parsed.raw_text or "").split()
                if len(text_parts) >= 2:
                    try:
                        request_id = UUID(text_parts[1])
                    except ValueError:
                        request_id = None
            if request_id is None:
                continue
            request = await svc.repo.get_request_by_id(request_id)
            if request is None:
                continue

            await svc.repo.create_message(
                ApprovalMessage(
                    approval_request_id=request.id,
                    direction="inbound",
                    channel="whatsapp",
                    provider_message_id=parsed.provider_message_id,
                    message_type="text",
                    raw_text=parsed.raw_text,
                    parsed_intent=parsed.intent,
                    intent_confidence=parsed.confidence,
                    user_feedback=parsed.feedback,
                    payload={"raw_text": parsed.raw_text or ""},
                )
            )
            request.responded_at = datetime.now(timezone.utc)
            await svc._apply_intent(request, parsed.intent, parsed.feedback)
            await svc.audit.record(
                tenant_id=request.tenant_id,
                actor_user_id=None,
                action="approvals.response_received",
                entity_type="approval_request",
                entity_id=str(request.id),
                message="Approval response processed",
                payload={"intent": parsed.intent, "confidence": f"{parsed.confidence:.2f}"},
            )
            updated_requests.append(request)
    except Exception as exc:
        inbox.status = "error"
        inbox.error_message = str(exc)
        await svc.db.commit()
        raise

    inbox.status = "processed"
    inbox.processed_at = datetime.now(timezone.utc)
    await svc.db.commit()
    return updated_requests


