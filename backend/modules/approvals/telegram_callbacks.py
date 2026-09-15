from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.modules.approvals.models import (
    ApprovalIntent,
    ApprovalMessage,
    ApprovalRequest,
    ApprovalStatus,
)
from backend.modules.approvals.providers import (
    TelegramProvider,
    get_telegram_provider,
    verify_signed_callback_data,
)
from backend.modules.story_intelligence.models import TrendCandidateStatus, TrendWorkflowState


class _TelegramDeps(Protocol):
    db: AsyncSession
    repo: Any
    settings_service: Any
    audit: Any
    content_repo: Any
    content_service: Any
    story_repo: Any

    async def _record_callback_failure(self, request: ApprovalRequest | None, *, callback_data: str, reason: str) -> None: ...
    async def _apply_intent(self, request: ApprovalRequest, intent: str, feedback: str | None) -> None: ...
    async def send_publish_for_approval(self, **kwargs: Any) -> ApprovalRequest: ...


async def handle_telegram_callback(
    svc,
    payload: dict[str, Any],
) -> None:
    """
    Process an inline keyboard callback_query from Telegram (Gate 2 — asset approval).
    Acks the popup, applies intent, and edits the approval card in-place to reflect the outcome.
    """
    callback_query = payload.get("callback_query")
    if not callback_query:
        return

    callback_query_id = callback_query.get("id", "")
    data = callback_query.get("data", "")
    # Extract message context for in-place editing
    tg_message = callback_query.get("message", {})
    cb_message_id = str(tg_message.get("message_id", ""))
    cb_chat_id = str(tg_message.get("chat", {}).get("id", ""))

    is_valid, intent_str, request_id_str = verify_signed_callback_data(data)
    request: ApprovalRequest | None = None
    try:
        request_uuid = UUID(request_id_str)
        request = await svc.repo.get_request_by_id(request_uuid)
    except ValueError:
        request_uuid = None
    if not is_valid:
        await svc._record_callback_failure(request, callback_data=data, reason="invalid_signature")
        await svc.db.commit()
        return

    if not request:
        return

    try:
        telegram_config = await svc.settings_service.resolve_telegram_runtime_config(request.tenant_id)
        bot_token = str(telegram_config.get("bot_token", ""))
        # Prefer chat_id from the callback payload (most reliable); fall back to config
        chat_id = cb_chat_id or str(telegram_config.get("chat_id", ""))
    except Exception:
        bot_token = ""
        chat_id = cb_chat_id

    edited_text: str | None = None
    if intent_str in {"approve", "approve_topic", "approve_publish"}:
        request.responded_at = datetime.now(timezone.utc)
        if request.approval_type == "topic" and request.related_entity_id:
            candidate = await svc.story_repo.get_trend_candidate(request.tenant_id, UUID(request.related_entity_id))
            if candidate:
                candidate.status = TrendCandidateStatus.APPROVED_TOPIC.value
            request.status = ApprovalStatus.APPROVED.value
            request.response_payload_json = {"decision": "approved_topic"}
            ack_text = "✅ Topic approved."
            edited_text = "📡 Topic Approval — ✅ <b>APPROVED</b>."
        else:
            ack_text = "✅ Approved."
            edited_text = "✅ <b>APPROVED</b>."
            try:
                await svc._apply_intent(request, ApprovalIntent.APPROVE.value, None)
                if request.approval_type == "asset" and request.content_job_id:
                    content_job = await svc.content_repo.get_job(request.tenant_id, request.content_job_id)
                    if content_job:
                        plan = await svc.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
                        if plan:
                            cluster = await svc.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
                            if cluster:
                                cluster.workflow_state = TrendWorkflowState.PUBLISH_READY.value
                    ack_text = "✅ Assets approved and queued for publishing."
                    edited_text = "🎨 Content Asset — ✅ <b>APPROVED</b> — queued for publishing."
                elif request.approval_type == "publish":
                    ack_text = "✅ Publish approved."
                    edited_text = "🚀 Publish Approval — ✅ <b>APPROVED</b>."
            except Exception:
                ack_text = "✅ Approved — follow-up action failed."
                edited_text = "✅ <b>APPROVED</b> (follow-up action failed)."
    elif intent_str in {"reject", "reject_topic"}:
        request.responded_at = datetime.now(timezone.utc)
        if request.approval_type == "topic" and request.related_entity_id:
            candidate = await svc.story_repo.get_trend_candidate(request.tenant_id, UUID(request.related_entity_id))
            if candidate:
                candidate.status = TrendCandidateStatus.REJECTED_TOPIC.value
            request.status = ApprovalStatus.REJECTED.value
            request.response_payload_json = {"decision": "rejected_topic"}
            ack_text = "❌ Topic rejected."
            edited_text = "📡 Topic Approval — ❌ <b>REJECTED</b>."
        else:
            await svc._apply_intent(request, ApprovalIntent.REJECT.value, None)
            if request.content_job_id:
                content_job = await svc.content_repo.get_job(request.tenant_id, request.content_job_id)
                if content_job:
                    plan = await svc.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
                    if plan:
                        cluster = await svc.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
                        if cluster:
                            cluster.workflow_state = TrendWorkflowState.REJECTED.value
            ack_text = "❌ Rejected."
            edited_text = "❌ <b>REJECTED</b>."
    elif intent_str == "revise":
        # Set a Redis session so the next plain-text message from this chat is treated as revision feedback
        if chat_id:
            await redis_client.setex(
                f"approval:pending_revision:{chat_id}",
                600,  # 10-minute window
                str(request.id),
            )
        request.status = ApprovalStatus.PENDING.value
        content_job = (
            await svc.content_repo.get_job(request.tenant_id, request.content_job_id)
            if request.content_job_id is not None
            else None
        )
        if content_job:
            plan = await svc.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
            if plan:
                cluster = await svc.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.ASSET_GENERATION.value
        ack_text = "✏️ Send your revision notes as a reply in this chat (10 min window)."
        edited_text = "🎨 Content Asset — ✏️ <b>REVISION REQUESTED</b> — awaiting your feedback message."
    elif intent_str in {"trim", "edit_cta"}:
        if cb_chat_id:
            await redis_client.setex(
                f"approval:pending_revision:{cb_chat_id}",
                600,
                str(request.id),
            )
        request.status = ApprovalStatus.PENDING.value
        request.response_payload_json = {"revision_mode": intent_str}
        ack_text = "✏️ Send your notes in chat."
        edited_text = f"🎨 Content Asset — ✏️ <b>{intent_str.replace('_', ' ').upper()}</b> requested."
    elif intent_str == "publish_gate":
        if not request.content_job_id:
            return
        assets = await svc.content_repo.list_assets(request.content_job_id)
        platforms = sorted({asset.platform for asset in assets if asset.platform})
        publish_request = await svc.send_publish_for_approval(
            tenant_id=request.tenant_id,
            content_job_id=request.content_job_id,
            platforms=platforms,
            recipient=request.recipient,
        )
        ack_text = "🚀 Publish approval sent."
        edited_text = f"🎨 Content Asset — 🚀 <b>PUBLISH GATE SENT</b> ({publish_request.id})."
    elif intent_str in {"hold_topic", "hold_publish"}:
        request.status = ApprovalStatus.PENDING.value
        request.response_payload_json = {"decision": "held"}
        ack_text = "⏸ Held."
        edited_text = "⏸ <b>HELD</b>."
    elif intent_str in {"cancel_publish"}:
        request.status = ApprovalStatus.REJECTED.value
        request.response_payload_json = {"decision": "cancelled"}
        ack_text = "🛑 Publish cancelled."
        edited_text = "🚀 Publish Approval — 🛑 <b>CANCELLED</b>."
    elif intent_str in {"schedule_publish"}:
        request.status = ApprovalStatus.PENDING.value
        request.response_payload_json = {
            **(request.response_payload_json or {}),
            "scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        }
        ack_text = "🕒 Scheduled for later."
        edited_text = "🚀 Publish Approval — 🕒 <b>SCHEDULED FOR LATER</b>."
    elif intent_str.startswith("approve_") and request.approval_type == "publish":
        platform = intent_str.removeprefix("approve_")
        request.response_payload_json = {
            **(request.response_payload_json or {}),
            "platforms": [platform],
        }
        await svc._apply_intent(request, ApprovalIntent.APPROVE.value, None)
        ack_text = f"✅ Publish approved for {platform}."
        edited_text = f"🚀 Publish Approval — ✅ <b>{platform.upper()} APPROVED</b>."
    elif intent_str in {"safer_topic", "regen_topic"}:
        request.status = ApprovalStatus.REVISION_REQUESTED.value
        request.response_payload_json = {"decision": intent_str}
        ack_text = "♻️ Topic routed for safer brief regeneration."
        edited_text = "📡 Topic Approval — ♻️ <b>SAFER BRIEF REQUESTED</b>."
    else:
        return

    await svc.repo.create_message(
        ApprovalMessage(
            approval_request_id=request.id,
            direction="inbound",
            channel="telegram",
            message_type="callback",
            raw_text=data,
            parsed_intent=intent_str,
            intent_confidence=1.0,
            payload={"callback_data": data, "chat_id": cb_chat_id, "message_id": cb_message_id},
        )
    )
    request.responded_by = f"telegram:{cb_chat_id}" if cb_chat_id else "telegram"

    if bot_token:
        try:
            provider = (
                get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
                if not bot_token or bot_token.startswith("mock")
                else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
            )
            if callback_query_id:
                await provider.answer_callback(callback_query_id, ack_text)
            # Edit the approval card in-place — use stored message_id or the one from the callback
            edit_message_id = cb_message_id or request.telegram_message_id
            if edit_message_id and chat_id and edited_text:
                await provider.edit_message(
                    chat_id=chat_id,
                    message_id=edit_message_id,
                    new_text=edited_text,
                )
        except Exception:
            pass  # Ack/edit failure must not roll back the approval state change

    await svc.audit.record(
        tenant_id=request.tenant_id,
        actor_user_id=None,
        action="approvals.telegram_callback",
        entity_type="approval_request",
        entity_id=str(request.id),
        message=f"Telegram callback: {intent_str}",
        payload={"intent": intent_str, "approval_type": request.approval_type},
        payload_schema="approval.telegram_callback.v1",
    )
    await svc.db.commit()


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

