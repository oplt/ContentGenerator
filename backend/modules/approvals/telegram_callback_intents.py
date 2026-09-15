"""Telegram callback intent handlers — one responsibility per function."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from backend.core.cache import redis_client
from backend.modules.approvals.models import ApprovalIntent, ApprovalRequest, ApprovalStatus
from backend.modules.story_intelligence.models import TrendCandidateStatus, TrendWorkflowState

REVISION_TTL_SECONDS = 600


@dataclass(frozen=True, slots=True)
class CallbackOutcome:
    ack_text: str
    edited_text: str


async def _set_revision_session(chat_id: str, request_id: UUID) -> None:
    if not chat_id:
        return
    await redis_client.setex(
        f"approval:pending_revision:{chat_id}",
        REVISION_TTL_SECONDS,
        str(request_id),
    )


async def _mark_job_cluster_state(svc: Any, request: ApprovalRequest, state: str) -> None:
    if request.content_job_id is None:
        return
    content_job = await svc.content_repo.get_job(request.tenant_id, request.content_job_id)
    if not content_job:
        return
    plan = await svc.content_service.plan_repo.get_content_plan(
        request.tenant_id, content_job.content_plan_id
    )
    if not plan:
        return
    cluster = await svc.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
    if cluster:
        cluster.workflow_state = state


async def handle_approve(
    svc: Any, request: ApprovalRequest, *, intent_str: str
) -> CallbackOutcome:
    request.responded_at = datetime.now(timezone.utc)
    if request.approval_type == "topic" and request.related_entity_id:
        candidate = await svc.story_repo.get_trend_candidate(
            request.tenant_id, UUID(request.related_entity_id)
        )
        if candidate:
            candidate.status = TrendCandidateStatus.APPROVED_TOPIC.value
        request.status = ApprovalStatus.APPROVED.value
        request.response_payload_json = {"decision": "approved_topic"}
        return CallbackOutcome("✅ Topic approved.", "📡 Topic Approval — ✅ <b>APPROVED</b>.")

    ack_text = "✅ Approved."
    edited_text = "✅ <b>APPROVED</b>."
    try:
        await svc._apply_intent(request, ApprovalIntent.APPROVE.value, None)
        if request.approval_type == "asset" and request.content_job_id:
            await _mark_job_cluster_state(
                svc, request, TrendWorkflowState.PUBLISH_READY.value
            )
            ack_text = "✅ Assets approved and queued for publishing."
            edited_text = "🎨 Content Asset — ✅ <b>APPROVED</b> — queued for publishing."
        elif request.approval_type == "publish":
            ack_text = "✅ Publish approved."
            edited_text = "🚀 Publish Approval — ✅ <b>APPROVED</b>."
    except Exception:
        ack_text = "✅ Approved — follow-up action failed."
        edited_text = "✅ <b>APPROVED</b> (follow-up action failed)."
    return CallbackOutcome(ack_text, edited_text)


async def handle_reject(svc: Any, request: ApprovalRequest) -> CallbackOutcome:
    request.responded_at = datetime.now(timezone.utc)
    if request.approval_type == "topic" and request.related_entity_id:
        candidate = await svc.story_repo.get_trend_candidate(
            request.tenant_id, UUID(request.related_entity_id)
        )
        if candidate:
            candidate.status = TrendCandidateStatus.REJECTED_TOPIC.value
        request.status = ApprovalStatus.REJECTED.value
        request.response_payload_json = {"decision": "rejected_topic"}
        return CallbackOutcome("❌ Topic rejected.", "📡 Topic Approval — ❌ <b>REJECTED</b>.")

    await svc._apply_intent(request, ApprovalIntent.REJECT.value, None)
    await _mark_job_cluster_state(svc, request, TrendWorkflowState.REJECTED.value)
    return CallbackOutcome("❌ Rejected.", "❌ <b>REJECTED</b>.")


async def handle_revise(svc: Any, request: ApprovalRequest, *, chat_id: str) -> CallbackOutcome:
    await _set_revision_session(chat_id, request.id)
    request.status = ApprovalStatus.PENDING.value
    await _mark_job_cluster_state(svc, request, TrendWorkflowState.ASSET_GENERATION.value)
    return CallbackOutcome(
        "✏️ Send your revision notes as a reply in this chat (10 min window).",
        "🎨 Content Asset — ✏️ <b>REVISION REQUESTED</b> — awaiting your feedback message.",
    )


async def handle_trim_or_cta(
    request: ApprovalRequest, *, chat_id: str, intent_str: str
) -> CallbackOutcome:
    await _set_revision_session(chat_id, request.id)
    request.status = ApprovalStatus.PENDING.value
    request.response_payload_json = {"revision_mode": intent_str}
    label = intent_str.replace("_", " ").upper()
    return CallbackOutcome(
        "✏️ Send your notes in chat.",
        f"🎨 Content Asset — ✏️ <b>{label}</b> requested.",
    )


async def handle_publish_gate(svc: Any, request: ApprovalRequest) -> CallbackOutcome | None:
    if not request.content_job_id:
        return None
    assets = await svc.content_repo.list_assets(request.content_job_id)
    platforms = sorted({asset.platform for asset in assets if asset.platform})
    publish_request = await svc.send_publish_for_approval(
        tenant_id=request.tenant_id,
        content_job_id=request.content_job_id,
        platforms=platforms,
        recipient=request.recipient,
    )
    return CallbackOutcome(
        "🚀 Publish approval sent.",
        f"🎨 Content Asset — 🚀 <b>PUBLISH GATE SENT</b> ({publish_request.id}).",
    )


def handle_hold(request: ApprovalRequest) -> CallbackOutcome:
    request.status = ApprovalStatus.PENDING.value
    request.response_payload_json = {"decision": "held"}
    return CallbackOutcome("⏸ Held.", "⏸ <b>HELD</b>.")


def handle_cancel_publish(request: ApprovalRequest) -> CallbackOutcome:
    request.status = ApprovalStatus.REJECTED.value
    request.response_payload_json = {"decision": "cancelled"}
    return CallbackOutcome(
        "🛑 Publish cancelled.",
        "🚀 Publish Approval — 🛑 <b>CANCELLED</b>.",
    )


def handle_schedule_publish(request: ApprovalRequest) -> CallbackOutcome:
    request.status = ApprovalStatus.PENDING.value
    request.response_payload_json = {
        **(request.response_payload_json or {}),
        "scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    }
    return CallbackOutcome(
        "🕒 Scheduled for later.",
        "🚀 Publish Approval — 🕒 <b>SCHEDULED FOR LATER</b>.",
    )


async def handle_approve_platform(
    svc: Any, request: ApprovalRequest, *, intent_str: str
) -> CallbackOutcome:
    platform = intent_str.removeprefix("approve_")
    request.response_payload_json = {
        **(request.response_payload_json or {}),
        "platforms": [platform],
    }
    await svc._apply_intent(request, ApprovalIntent.APPROVE.value, None)
    return CallbackOutcome(
        f"✅ Publish approved for {platform}.",
        f"🚀 Publish Approval — ✅ <b>{platform.upper()} APPROVED</b>.",
    )


def handle_safer_topic(request: ApprovalRequest, *, intent_str: str) -> CallbackOutcome:
    request.status = ApprovalStatus.REVISION_REQUESTED.value
    request.response_payload_json = {"decision": intent_str}
    return CallbackOutcome(
        "♻️ Topic routed for safer brief regeneration.",
        "📡 Topic Approval — ♻️ <b>SAFER BRIEF REQUESTED</b>.",
    )


async def dispatch_intent(
    svc: Any,
    request: ApprovalRequest,
    *,
    intent_str: str,
    chat_id: str,
    cb_chat_id: str,
) -> CallbackOutcome | None:
    """Route callback intent → outcome. None means ignore (no state change)."""
    if intent_str in {"approve", "approve_topic", "approve_publish"}:
        return await handle_approve(svc, request, intent_str=intent_str)
    if intent_str in {"reject", "reject_topic"}:
        return await handle_reject(svc, request)
    if intent_str == "revise":
        return await handle_revise(svc, request, chat_id=chat_id)
    if intent_str in {"trim", "edit_cta"}:
        return await handle_trim_or_cta(request, chat_id=cb_chat_id, intent_str=intent_str)
    if intent_str == "publish_gate":
        return await handle_publish_gate(svc, request)
    if intent_str in {"hold_topic", "hold_publish"}:
        return handle_hold(request)
    if intent_str == "cancel_publish":
        return handle_cancel_publish(request)
    if intent_str == "schedule_publish":
        return handle_schedule_publish(request)
    if intent_str.startswith("approve_") and request.approval_type == "publish":
        return await handle_approve_platform(svc, request, intent_str=intent_str)
    if intent_str in {"safer_topic", "regen_topic"}:
        return handle_safer_topic(request, intent_str=intent_str)
    return None
