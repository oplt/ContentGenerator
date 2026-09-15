from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.approvals.approval_helpers import (
    build_summary_text,
    build_telegram_asset_previews,
    create_or_refresh_request,
    risk_payload_for_job,
    telegram_runtime,
)
from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage, ApprovalRequest
from backend.modules.approvals.providers import get_whatsapp_provider
from backend.modules.story_intelligence.models import TrendWorkflowState


async def send_for_approval(
    svc,
    *,
    tenant_id: UUID,
    content_job_id: UUID,
    recipient: str | None,
) -> ApprovalRequest:
    runtime_config = await svc.settings_service.resolve_whatsapp_runtime_config(tenant_id)
    resolved_recipient = (recipient or runtime_config.recipient or settings.WHATSAPP_DEFAULT_RECIPIENT).strip()
    if not resolved_recipient:
        raise HTTPException(status_code=400, detail="No approval recipient configured for this tenant")

    content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
    if not content_job:
        raise HTTPException(status_code=404, detail="Content job not found")
    risk_payload = risk_payload_for_job(content_job)
    if risk_payload["risk_label"] == "blocked":
        raise HTTPException(status_code=422, detail="Risk review blocked this content from operator approval")
    request = await create_or_refresh_request(svc, 
        tenant_id=tenant_id,
        content_job_id=content_job_id,
        recipient=resolved_recipient,
        provider="telegram",
        approval_type="asset",
        related_entity_type="content_job",
        related_entity_id=str(content_job_id),
        buttons_json=["approve", "reject", "revise", "trim", "edit_cta", "publish_gate"],
    )

    telegram_config, telegram = await telegram_runtime(svc, tenant_id)
    if telegram:
        headline, platform_previews = await build_telegram_asset_previews(svc, tenant_id, content_job_id)
        tg_result = await telegram.send_asset_card(
            headline=headline,
            platform_previews=platform_previews,
            approval_request_id=str(request.id),
            risk_level=str(risk_payload["risk_label"]),
        )
        request.provider_request_id = tg_result.get("message_id")
        request.telegram_message_id = tg_result.get("message_id")
        request.last_sent_at = datetime.now(timezone.utc)
        await svc.repo.create_message(
            ApprovalMessage(
                approval_request_id=request.id,
                direction="outbound",
                channel="telegram",
                provider_message_id=tg_result.get("message_id"),
                message_type="asset_card",
                raw_text=headline,
                parsed_intent=ApprovalIntent.UNKNOWN.value,
                intent_confidence=1.0,
                payload=tg_result,
            )
        )
    else:
        provider = get_whatsapp_provider(runtime_config)
        message_text = await build_summary_text(svc, tenant_id, content_job_id, request.id)
        send_result = await provider.send_message(to=request.recipient, text=message_text)
        request.channel = "whatsapp"
        request.provider = runtime_config.provider
        request.provider_request_id = send_result.get("message_id")
        request.last_sent_at = datetime.now(timezone.utc)
        await svc.repo.create_message(
            ApprovalMessage(
                approval_request_id=request.id,
                direction="outbound",
                channel="whatsapp",
                provider_message_id=send_result.get("message_id"),
                message_type="text",
                raw_text=message_text,
                parsed_intent=ApprovalIntent.UNKNOWN.value,
                intent_confidence=1.0,
                payload=send_result,
            )
        )

    request.response_payload_json = {
        **request.response_payload_json,
        **risk_payload,
    }

    if content_job:
        plan = await svc.content_service.plan_repo.get_content_plan(tenant_id, content_job.content_plan_id)
        if plan:
            cluster = await svc.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
            if cluster:
                cluster.workflow_state = TrendWorkflowState.ASSET_REVIEW.value

    await svc.audit.record(
        tenant_id=tenant_id,
        actor_user_id=None,
        action="approvals.request_sent",
        entity_type="approval_request",
        entity_id=str(request.id),
        message="Approval request sent",
        payload={"content_job_id": str(content_job_id), "recipient": request.recipient, "approval_type": "asset"},
        payload_schema="approval.request.v1",
    )
    await svc.db.flush()
    return request


async def send_topic_for_approval(
    svc,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    recipient: str | None = None,
) -> ApprovalRequest:
    candidate = await svc.story_repo.get_trend_candidate(tenant_id, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Trend candidate not found")
    telegram_config, telegram = await telegram_runtime(svc, tenant_id)
    resolved_recipient = recipient or str(telegram_config.get("chat_id", "") or settings.WHATSAPP_DEFAULT_RECIPIENT)
    request = await create_or_refresh_request(svc, 
        tenant_id=tenant_id,
        content_job_id=None,
        recipient=resolved_recipient,
        provider="telegram",
        approval_type="topic",
        related_entity_type="trend_candidate",
        related_entity_id=str(candidate.id),
        buttons_json=["approve_topic", "reject_topic", "safer_topic", "hold_topic", "regen_topic"],
        expires_in_hours=18,
    )
    if not telegram:
        raise HTTPException(status_code=422, detail="Telegram is not configured for topic approvals")
    score_explanation = cast(dict[str, object], candidate.score_explanation or {})
    cluster_explainability = cast(dict[str, object], score_explanation.get("cluster_explainability", {}))
    tg_result = await telegram.send_topic_card(
        title=candidate.primary_topic,
        score=candidate.final_score,
        why_now=str(cluster_explainability.get("why_now", "Emerging trend")),
        evidence_links=candidate.evidence_links,
        risk_level=str(score_explanation.get("review_risk_label", score_explanation.get("risk_level", "safe"))),
        callback_id=str(request.id),
    )
    request.response_payload_json = {
        **request.response_payload_json,
        "risk_label": str(score_explanation.get("review_risk_label", "low")),
        "topic_categories": score_explanation.get("topic_categories", []),
    }
    request.provider_request_id = tg_result.get("message_id")
    request.telegram_message_id = tg_result.get("message_id")
    request.last_sent_at = datetime.now(timezone.utc)
    await svc.repo.create_message(
        ApprovalMessage(
            approval_request_id=request.id,
            direction="outbound",
            channel="telegram",
            provider_message_id=tg_result.get("message_id"),
            message_type="topic_card",
            raw_text=candidate.primary_topic,
            parsed_intent=ApprovalIntent.UNKNOWN.value,
            intent_confidence=1.0,
            payload=tg_result,
        )
    )
    await svc.audit.record(
        tenant_id=tenant_id,
        actor_user_id=None,
        action="approvals.topic_sent",
        entity_type="approval_request",
        entity_id=str(request.id),
        message="Topic approval request sent",
        payload={"trend_candidate_id": str(candidate.id)},
        payload_schema="approval.topic.v1",
    )
    await svc.db.flush()
    return request


async def send_publish_for_approval(
    svc,
    *,
    tenant_id: UUID,
    content_job_id: UUID,
    platforms: list[str],
    scheduled_for: datetime | None = None,
    recipient: str | None = None,
) -> ApprovalRequest:
    telegram_config, telegram = await telegram_runtime(svc, tenant_id)
    resolved_recipient = recipient or str(telegram_config.get("chat_id", "") or settings.WHATSAPP_DEFAULT_RECIPIENT)
    content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
    if not content_job:
        raise HTTPException(status_code=404, detail="Content job not found")
    risk_payload = risk_payload_for_job(content_job)
    if risk_payload["risk_label"] == "blocked":
        raise HTTPException(status_code=422, detail="Risk review blocked this content from publish approval")
    request = await create_or_refresh_request(svc, 
        tenant_id=tenant_id,
        content_job_id=content_job_id,
        recipient=resolved_recipient,
        provider="telegram",
        approval_type="publish",
        related_entity_type="content_job",
        related_entity_id=str(content_job_id),
        buttons_json=["approve_publish", "hold_publish", "cancel_publish", "schedule_publish", *[f"approve_{platform}" for platform in platforms]],
        expires_in_hours=24,
    )
    request.response_payload_json = {
        "platforms": platforms,
        "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
    }
    request.response_payload_json = {
        **request.response_payload_json,
        **risk_payload,
    }
    if not telegram:
        raise HTTPException(status_code=422, detail="Telegram is not configured for publish approvals")
    headline = (
        str(content_job.grounding_bundle.get("headline", "Ready to publish"))
        if content_job
        else "Ready to publish"
    )
    tg_result = await telegram.send_publish_card(
        headline=headline,
        approval_request_id=str(request.id),
        platforms=platforms,
        scheduled_for=scheduled_for.isoformat() if scheduled_for else None,
        risk_level=str(risk_payload["risk_label"]),
    )
    request.provider_request_id = tg_result.get("message_id")
    request.telegram_message_id = tg_result.get("message_id")
    request.last_sent_at = datetime.now(timezone.utc)
    await svc.repo.create_message(
        ApprovalMessage(
            approval_request_id=request.id,
            direction="outbound",
            channel="telegram",
            provider_message_id=tg_result.get("message_id"),
            message_type="publish_card",
            raw_text=headline,
            parsed_intent=ApprovalIntent.UNKNOWN.value,
            intent_confidence=1.0,
            payload=tg_result,
        )
    )
    await svc.audit.record(
        tenant_id=tenant_id,
        actor_user_id=None,
        action="approvals.publish_sent",
        entity_type="approval_request",
        entity_id=str(request.id),
        message="Publish approval request sent",
        payload={"content_job_id": str(content_job_id), "platforms": platforms},
        payload_schema="approval.publish.v1",
    )
    await svc.db.flush()
    return request


