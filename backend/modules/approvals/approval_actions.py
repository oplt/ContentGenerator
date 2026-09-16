from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException

from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage, ApprovalRequest, ApprovalStatus
from backend.modules.approvals.schemas import ApprovalRequestResponse
from backend.modules.publishing.schemas import PublishNowRequest


async def record_preference(
    svc, tenant_id: UUID, content_job_id: UUID, outcome: str
) -> None:
    """
    Update per-tenant content preference EMA: track approve/revise/reject rate
    per (platform, tone) pair. Stored as JSON in tenant settings under
    'preferences.content_outcomes'.
    """
    try:
        content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
        if not content_job:
            return
        from backend.modules.content_strategy.repository import ContentStrategyRepository
        plan = await ContentStrategyRepository(svc.db).get_content_plan(
            tenant_id, content_job.content_plan_id
        )
        if not plan:
            return
        key = f"{','.join(sorted(plan.target_platforms))}|{plan.tone}"
        tenant = await svc.settings_service.get_tenant_settings(tenant_id)
        prefs: dict[str, Any] = {}
        try:
            import json as _json
            raw = (tenant.settings or {}).get("preferences.content_outcomes", "{}")
            prefs = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            pass
        entry = prefs.get(key, {"approve": 0, "revise": 0, "reject": 0, "total": 0})
        entry[outcome] = entry.get(outcome, 0) + 1
        entry["total"] = entry.get("total", 0) + 1
        prefs[key] = entry
        import json as _json
        current_settings = dict(tenant.settings or {})
        current_settings["preferences.content_outcomes"] = _json.dumps(prefs)
        tenant.settings = current_settings
        await svc.db.flush()
    except Exception:
        pass  # Preference tracking must never block the approval flow


async def record_callback_failure(
    svc,
    request: ApprovalRequest | None,
    *,
    callback_data: str,
    reason: str,
) -> None:
    if request:
        request.callback_verification_failures += 1
        request.callback_last_error = reason
        await svc.repo.create_message(
            ApprovalMessage(
                approval_request_id=request.id,
                direction="inbound",
                channel="telegram",
                message_type="callback_failure",
                raw_text=callback_data,
                parsed_intent=ApprovalIntent.UNKNOWN.value,
                intent_confidence=0.0,
                payload={"callback_data": callback_data, "error": reason},
            )
        )
        await svc.audit.record(
            tenant_id=request.tenant_id,
            actor_user_id=None,
            action="approvals.telegram_callback_failed",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Telegram callback verification failed",
            payload={"error": reason},
            severity="warning",
            outcome="failed",
            payload_schema="approval.telegram_callback_failure.v1",
        )
    else:
        await svc.audit.record(
            tenant_id=None,
            actor_user_id=None,
            action="approvals.telegram_callback_failed",
            entity_type="approval_request",
            entity_id=None,
            message="Telegram callback verification failed without resolvable request",
            payload={"error": reason, "callback_data": callback_data},
            severity="warning",
            outcome="failed",
            payload_schema="approval.telegram_callback_failure.v1",
        )


async def resend_request(
    svc, tenant_id: UUID, request_id: UUID) -> ApprovalRequest:
    request = await svc.repo.get_request(tenant_id, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if request.approval_type == "asset":
        if request.content_job_id is None:
            raise HTTPException(status_code=422, detail="Approval request has no content job")
        return await svc.send_for_approval(tenant_id=tenant_id,
            content_job_id=request.content_job_id,
            recipient=request.recipient,
        )
    if request.approval_type == "publish":
        if request.content_job_id is None:
            raise HTTPException(status_code=422, detail="Approval request has no content job")
        payload = request.response_payload_json or {}
        scheduled_for_value = payload.get("scheduled_for")
        return await svc.send_publish_for_approval(tenant_id=tenant_id,
            content_job_id=request.content_job_id,
            platforms=list(cast(list[str], payload.get("platforms", []))),
            scheduled_for=datetime.fromisoformat(scheduled_for_value) if isinstance(scheduled_for_value, str) else None,
            recipient=request.recipient,
        )
    if request.approval_type == "topic" and request.related_entity_id:
        return await svc.send_topic_for_approval(tenant_id=tenant_id,
            candidate_id=UUID(request.related_entity_id),
            recipient=request.recipient,
        )
    raise HTTPException(status_code=422, detail="Approval request type cannot be resent")


async def operator_action(
    svc,
    *,
    tenant_id: UUID,
    request_id: UUID,
    action: str,
    feedback: str | None,
    actor_user_id: UUID | None,
) -> ApprovalRequestResponse:
    request = await svc.repo.get_request(tenant_id, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    normalized = action.lower()
    if normalized == "regenerate":
        if not request.content_job_id:
            raise HTTPException(status_code=422, detail="Regenerate is only supported for content-backed approvals")
        revised_job = await svc.content_service.regenerate_with_feedback(
            tenant_id=tenant_id,
            job_id=request.content_job_id,
            feedback=feedback or "Regenerate with a fresher angle and tighter structure.",
            requested_by_user_id=actor_user_id,
            source_channel="dashboard",
        )
        request.content_job_id = revised_job.id
        request.status = ApprovalStatus.PENDING.value
        request.revision_count += 1
    elif normalized == "approve":
        await apply_intent(svc, request, ApprovalIntent.APPROVE.value, feedback)
    elif normalized == "reject":
        await apply_intent(svc, request, ApprovalIntent.REJECT.value, feedback)
    elif normalized == "revise":
        await apply_intent(svc, request, ApprovalIntent.REVISE.value, feedback)
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported approval action '{action}'")
    request.responded_by = str(actor_user_id) if actor_user_id else "dashboard"
    request.responded_at = datetime.now(timezone.utc)
    await svc.db.flush()
    return await svc.get_request_detail(tenant_id, request.id)


async def _apply_approve(svc: Any, request: ApprovalRequest) -> None:
    request.status = ApprovalStatus.APPROVED.value
    if not request.content_job_id:
        return
    await record_preference(svc, request.tenant_id, request.content_job_id, "approve")
    # Workflow-bound approvals: PublishNode owns publishing (avoid double publish).
    from backend.modules.workflows.approval_binding import get_workflow_binding

    if get_workflow_binding(request) is not None:
        return
    payload = request.response_payload_json or {}
    scheduled_for_value = payload.get("scheduled_for")
    if request.approval_type == "publish":
        await svc.publish_service.publish_now(
            tenant_id=request.tenant_id,
            approval_request_id=request.id,
            payload=PublishNowRequest(
                content_job_id=request.content_job_id,
                platforms=list(cast(list[str], payload.get("platforms", []))) or None,
                scheduled_for=(
                    datetime.fromisoformat(scheduled_for_value)
                    if isinstance(scheduled_for_value, str)
                    else None
                ),
            ),
        )
        return
    if request.approval_type == "asset":
        await svc.publish_service.publish_now(
            tenant_id=request.tenant_id,
            approval_request_id=request.id,
            payload=PublishNowRequest(content_job_id=request.content_job_id),
        )


async def _apply_revise(svc: Any, request: ApprovalRequest, feedback: str) -> None:
    max_revisions = 5
    if request.revision_count >= max_revisions:
        request.status = ApprovalStatus.REJECTED.value
        return
    request.status = ApprovalStatus.REVISION_REQUESTED.value
    request.revision_count += 1
    if not request.content_job_id:
        return
    await record_preference(svc, request.tenant_id, request.content_job_id, "revise")
    revised_job = await svc.content_service.regenerate_with_feedback(
        tenant_id=request.tenant_id,
        job_id=request.content_job_id,
        feedback=feedback,
        requested_by_user_id=None,
        source_channel=request.channel,
    )
    request.content_job_id = revised_job.id
    request.status = ApprovalStatus.PENDING.value
    await svc.send_for_approval(
        tenant_id=request.tenant_id,
        content_job_id=revised_job.id,
        recipient=request.recipient,
    )


async def _apply_reject(svc: Any, request: ApprovalRequest) -> None:
    request.status = ApprovalStatus.REJECTED.value
    if request.content_job_id:
        await record_preference(svc, request.tenant_id, request.content_job_id, "reject")


async def apply_intent(
    svc: Any, request: ApprovalRequest, intent: str, feedback: str | None
) -> None:
    """Shared intent dispatch used by both WhatsApp and Telegram handlers."""
    if intent == ApprovalIntent.APPROVE.value:
        await _apply_approve(svc, request)
    elif intent == ApprovalIntent.REVISE.value and feedback:
        await _apply_revise(svc, request, feedback)
    elif intent == ApprovalIntent.REJECT.value:
        await _apply_reject(svc, request)
    else:
        return

    await svc.audit.record(
        tenant_id=request.tenant_id,
        actor_user_id=None,
        action="approvals.decision",
        entity_type="approval_request",
        entity_id=str(request.id),
        message=f"Approval decision applied: {intent}",
        payload={
            "intent": intent,
            "content_job_id": str(request.content_job_id) if request.content_job_id else None,
            "has_feedback": bool(feedback),
        },
        outcome="success",
        payload_schema="approval.decision.v1",
    )

    # Durable workflow resume — no-op when request is not workflow-bound.
    from backend.modules.workflows.approval_binding import maybe_resume_workflow_from_approval

    await maybe_resume_workflow_from_approval(svc.db, request)


