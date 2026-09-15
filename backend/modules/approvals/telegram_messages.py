from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from backend.core.cache import redis_client
from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage


async def handle_telegram_message(svc, payload: dict[str, Any]) -> bool:
    """
    Handle a plain-text Telegram message. If a revision session is pending for
    this chat, apply the message text as revision feedback.
    Returns True if the message was consumed as revision feedback.
    """
    message = payload.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not text or not chat_id:
        return False

    session_key = f"approval:pending_revision:{chat_id}"
    pending_request_id_bytes = await redis_client.get(session_key)
    if not pending_request_id_bytes:
        return False

    try:
        request_id = UUID(pending_request_id_bytes.decode())
    except (ValueError, AttributeError):
        return False

    await redis_client.delete(session_key)
    request = await svc.repo.get_request_by_id(request_id)
    if request is None:
        return False

    request.responded_at = datetime.now(timezone.utc)
    request.responded_by = f"telegram:{chat_id}"
    await svc._apply_intent(request, ApprovalIntent.REVISE.value, text)
    await svc.repo.create_message(
        ApprovalMessage(
            approval_request_id=request.id,
            direction="inbound",
            channel="telegram",
            message_type="text",
            raw_text=text,
            parsed_intent=ApprovalIntent.REVISE.value,
            intent_confidence=0.95,
            user_feedback=text,
            payload={"chat_id": chat_id},
        )
    )
    await svc.audit.record(
        tenant_id=request.tenant_id,
        actor_user_id=None,
        action="approvals.telegram_revision",
        entity_type="approval_request",
        entity_id=str(request.id),
        message="Telegram revision feedback received",
        payload={"feedback_length": len(text)},
        payload_schema="approval.telegram_revision.v1",
    )
    await svc.db.commit()
    return True
