from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage, ApprovalRequest, ApprovalStatus, WebhookInbox
from backend.modules.approvals.providers import (
    TelegramProvider,
    get_telegram_provider,
    WhatsAppRuntimeConfig,
    get_whatsapp_provider,
    verify_signed_callback_data,
)
from backend.modules.approvals.repository import ApprovalRepository
from backend.modules.approvals.telegram_callbacks import (
    handle_telegram_callback as _handle_telegram_callback,
    handle_telegram_message as _handle_telegram_message,
)
from backend.modules.approvals.webhook_processing import (
    handle_webhook as _handle_webhook,
    process_webhook_inbox as _process_webhook_inbox,
)
from backend.modules.approvals.schemas import ApprovalMessageResponse, ApprovalRequestResponse
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.publishing.schemas import PublishNowRequest
from backend.modules.publishing.service import PublishingService
from backend.modules.settings.service import SettingsService
from backend.modules.story_intelligence.models import TrendCandidateStatus, TrendWorkflowState
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class ApprovalService:
    """
    Approval workflows.

    Telegram/WhatsApp webhook handlers act as entrypoints and may ``commit()``
    deliberately for durable inbox/callback state. Celery callers rely on
    ``run_async_task`` for the final commit (services should flush).
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ApprovalRepository(db)
        self.content_repo = ContentGenerationRepository(db)
        self.content_service = ContentGenerationService(db)
        self.publish_service = PublishingService(db)
        self.settings_service = SettingsService(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.brief_repo = EditorialBriefRepository(db)
        self.audit = AuditService(db)

    @staticmethod
    def _risk_payload_for_job(content_job: Any) -> dict[str, object]:
        grounding = content_job.grounding_bundle if isinstance(getattr(content_job, "grounding_bundle", None), dict) else {}
        review = grounding.get("risk_review", {})
        if not isinstance(review, dict):
            review = {}
        return {
            "risk_label": str(review.get("label") or grounding.get("risk_label") or "low"),
            "risk_review": review,
        }

    @staticmethod
    def _extract_phone_number_id(payload: dict[str, Any]) -> str | None:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                metadata = change.get("value", {}).get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                if phone_number_id:
                    return str(phone_number_id)
        return None

    async def _build_summary_text(self, tenant_id: UUID, content_job_id: UUID, approval_request_id: UUID) -> str:
        content_job = await self.content_repo.get_job(tenant_id, content_job_id)
        if not content_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.content_repo.list_assets(content_job.id)
        text_variants = [asset for asset in assets if asset.asset_type == "text_variant"]
        previews = [f"{asset.platform}/{asset.variant_label}: {asset.text_content}" for asset in text_variants[:4]]
        preview_text = "\n".join(previews)
        return (
            f"Approval request {approval_request_id}\n"
            "Reply with one of:\n"
            f"- APPROVE {approval_request_id}\n"
            f"- REVISE {approval_request_id} <feedback>\n"
            f"- REJECT {approval_request_id}\n\n"
            f"Preview:\n{preview_text}"
        )

    async def _build_telegram_asset_previews(self, tenant_id: UUID, content_job_id: UUID) -> tuple[str, list[str]]:
        """Returns (headline, list_of_platform_preview_strings) for the Telegram asset card."""
        content_job = await self.content_repo.get_job(tenant_id, content_job_id)
        headline = (
            str(content_job.grounding_bundle.get("headline", "Content ready for review"))
            if content_job
            else "Content ready for review"
        )
        if not content_job:
            return headline, []
        assets = await self.content_repo.list_assets(content_job.id)
        text_variants = [a for a in assets if a.asset_type == "text_variant"]
        previews = [f"[{(a.platform or 'UNKNOWN').upper()}] {(a.text_content or '')[:200]}" for a in text_variants[:3]]
        return headline, previews

    async def _telegram_runtime(self, tenant_id: UUID) -> tuple[dict[str, str | bool], TelegramProvider | None]:
        telegram_config = await self.settings_service.resolve_telegram_runtime_config(tenant_id)
        if not telegram_config.get("enabled") or not telegram_config.get("chat_id"):
            return telegram_config, None
        bot_token = str(telegram_config.get("bot_token", ""))
        chat_id = str(telegram_config.get("chat_id", ""))
        provider = (
            get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
            if bot_token.startswith("mock") or not bot_token
            else TelegramProvider(bot_token=bot_token, chat_id=chat_id)
        )
        return telegram_config, provider

    async def _create_or_refresh_request(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID | None,
        recipient: str,
        provider: str,
        approval_type: str,
        related_entity_type: str | None,
        related_entity_id: str | None,
        buttons_json: list[str],
        expires_in_hours: int = 48,
    ) -> ApprovalRequest:
        request = None
        if content_job_id:
            request = await self.repo.get_request_for_content_job(content_job_id)
        elif related_entity_type and related_entity_id:
            request = await self.repo.get_request_for_related_entity(
                tenant_id,
                related_entity_type,
                related_entity_id,
                approval_type,
            )
        if request:
            request.status = ApprovalStatus.PENDING.value
            request.recipient = recipient
            request.provider = provider
            request.approval_type = approval_type
            request.related_entity_type = related_entity_type
            request.related_entity_id = related_entity_id
            request.buttons_json = buttons_json
            request.expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
            request.callback_last_error = None
            await self.db.flush()
            return request
        return await self.repo.create_request(
            ApprovalRequest(
                tenant_id=tenant_id,
                content_job_id=content_job_id,
                status=ApprovalStatus.PENDING.value,
                channel="telegram",
                recipient=recipient,
                provider=provider,
                approval_type=approval_type,
                related_entity_type=related_entity_type,
                related_entity_id=related_entity_id,
                buttons_json=buttons_json,
                requested_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
            )
        )

    async def send_for_approval(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        recipient: str | None,
    ) -> ApprovalRequest:
        runtime_config = await self.settings_service.resolve_whatsapp_runtime_config(tenant_id)
        resolved_recipient = (recipient or runtime_config.recipient or settings.WHATSAPP_DEFAULT_RECIPIENT).strip()
        if not resolved_recipient:
            raise HTTPException(status_code=400, detail="No approval recipient configured for this tenant")

        content_job = await self.content_repo.get_job(tenant_id, content_job_id)
        if not content_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        risk_payload = self._risk_payload_for_job(content_job)
        if risk_payload["risk_label"] == "blocked":
            raise HTTPException(status_code=422, detail="Risk review blocked this content from operator approval")
        request = await self._create_or_refresh_request(
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            recipient=resolved_recipient,
            provider="telegram",
            approval_type="asset",
            related_entity_type="content_job",
            related_entity_id=str(content_job_id),
            buttons_json=["approve", "reject", "revise", "trim", "edit_cta", "publish_gate"],
        )

        telegram_config, telegram = await self._telegram_runtime(tenant_id)
        if telegram:
            headline, platform_previews = await self._build_telegram_asset_previews(tenant_id, content_job_id)
            tg_result = await telegram.send_asset_card(
                headline=headline,
                platform_previews=platform_previews,
                approval_request_id=str(request.id),
                risk_level=str(risk_payload["risk_label"]),
            )
            request.provider_request_id = tg_result.get("message_id")
            request.telegram_message_id = tg_result.get("message_id")
            request.last_sent_at = datetime.now(timezone.utc)
            await self.repo.create_message(
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
            message_text = await self._build_summary_text(tenant_id, content_job_id, request.id)
            send_result = await provider.send_message(to=request.recipient, text=message_text)
            request.channel = "whatsapp"
            request.provider = runtime_config.provider
            request.provider_request_id = send_result.get("message_id")
            request.last_sent_at = datetime.now(timezone.utc)
            await self.repo.create_message(
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
            plan = await self.content_service.plan_repo.get_content_plan(tenant_id, content_job.content_plan_id)
            if plan:
                cluster = await self.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.ASSET_REVIEW.value

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="approvals.request_sent",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Approval request sent",
            payload={"content_job_id": str(content_job_id), "recipient": request.recipient, "approval_type": "asset"},
            payload_schema="approval.request.v1",
        )
        await self.db.flush()
        return request

    async def send_topic_for_approval(
        self,
        *,
        tenant_id: UUID,
        candidate_id: UUID,
        recipient: str | None = None,
    ) -> ApprovalRequest:
        candidate = await self.story_repo.get_trend_candidate(tenant_id, candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Trend candidate not found")
        telegram_config, telegram = await self._telegram_runtime(tenant_id)
        resolved_recipient = recipient or str(telegram_config.get("chat_id", "") or settings.WHATSAPP_DEFAULT_RECIPIENT)
        request = await self._create_or_refresh_request(
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
        await self.repo.create_message(
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
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="approvals.topic_sent",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Topic approval request sent",
            payload={"trend_candidate_id": str(candidate.id)},
            payload_schema="approval.topic.v1",
        )
        await self.db.flush()
        return request

    async def send_publish_for_approval(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        platforms: list[str],
        scheduled_for: datetime | None = None,
        recipient: str | None = None,
    ) -> ApprovalRequest:
        telegram_config, telegram = await self._telegram_runtime(tenant_id)
        resolved_recipient = recipient or str(telegram_config.get("chat_id", "") or settings.WHATSAPP_DEFAULT_RECIPIENT)
        content_job = await self.content_repo.get_job(tenant_id, content_job_id)
        if not content_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        risk_payload = self._risk_payload_for_job(content_job)
        if risk_payload["risk_label"] == "blocked":
            raise HTTPException(status_code=422, detail="Risk review blocked this content from publish approval")
        request = await self._create_or_refresh_request(
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
        await self.repo.create_message(
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
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="approvals.publish_sent",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Publish approval request sent",
            payload={"content_job_id": str(content_job_id), "platforms": platforms},
            payload_schema="approval.publish.v1",
        )
        await self.db.flush()
        return request

    async def list_requests(self, tenant_id: UUID) -> list[ApprovalRequest]:
        return await self.repo.list_requests(tenant_id)

    async def get_request_detail(self, tenant_id: UUID, request_id: UUID) -> ApprovalRequestResponse:
        request = await self.repo.get_request(tenant_id, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found")
        messages = await self.repo.list_messages(request.id)
        return ApprovalRequestResponse(
            id=request.id,
            content_job_id=request.content_job_id,
            status=str(request.status),
            channel=request.channel,
            recipient=request.recipient,
            provider=request.provider,
            provider_request_id=request.provider_request_id,
            requested_at=request.requested_at,
            responded_at=request.responded_at,
            revision_count=request.revision_count,
            expires_at=request.expires_at,
            last_sent_at=request.last_sent_at,
            related_entity_type=request.related_entity_type,
            related_entity_id=request.related_entity_id,
            approval_type=request.approval_type,
            buttons_json=request.buttons_json,
            telegram_message_id=request.telegram_message_id,
            callback_verification_failures=request.callback_verification_failures,
            callback_last_error=request.callback_last_error,
            responded_by=request.responded_by,
            risk_label=str(request.response_payload_json.get("risk_label")) if request.response_payload_json.get("risk_label") else None,
            response_payload_json=request.response_payload_json,
            messages=[ApprovalMessageResponse.model_validate(message) for message in messages],
        )

    async def handle_webhook(
        self,
        *,
        payload: dict[str, Any],
        raw_body: bytes,
        signature: str | None,
    ) -> str:
        return await _handle_webhook(
            self, payload=payload, raw_body=raw_body, signature=signature
        )


    async def process_webhook_inbox(self, inbox_id: UUID) -> list[ApprovalRequest]:
        return await _process_webhook_inbox(self, inbox_id)


    async def _record_preference(
        self, tenant_id: UUID, content_job_id: UUID, outcome: str
    ) -> None:
        """
        Update per-tenant content preference EMA: track approve/revise/reject rate
        per (platform, tone) pair. Stored as JSON in tenant settings under
        'preferences.content_outcomes'.
        """
        try:
            content_job = await self.content_repo.get_job(tenant_id, content_job_id)
            if not content_job:
                return
            from backend.modules.content_strategy.repository import ContentStrategyRepository
            plan = await ContentStrategyRepository(self.db).get_content_plan(
                tenant_id, content_job.content_plan_id
            )
            if not plan:
                return
            key = f"{','.join(sorted(plan.target_platforms))}|{plan.tone}"
            tenant = await self.settings_service.get_tenant_settings(tenant_id)
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
            await self.db.flush()
        except Exception:
            pass  # Preference tracking must never block the approval flow

    async def _record_callback_failure(
        self,
        request: ApprovalRequest | None,
        *,
        callback_data: str,
        reason: str,
    ) -> None:
        if request:
            request.callback_verification_failures += 1
            request.callback_last_error = reason
            await self.repo.create_message(
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
            await self.audit.record(
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
            await self.audit.record(
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

    async def resend_request(self, tenant_id: UUID, request_id: UUID) -> ApprovalRequest:
        request = await self.repo.get_request(tenant_id, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if request.approval_type == "asset":
            if request.content_job_id is None:
                raise HTTPException(status_code=422, detail="Approval request has no content job")
            return await self.send_for_approval(
                tenant_id=tenant_id,
                content_job_id=request.content_job_id,
                recipient=request.recipient,
            )
        if request.approval_type == "publish":
            if request.content_job_id is None:
                raise HTTPException(status_code=422, detail="Approval request has no content job")
            payload = request.response_payload_json or {}
            scheduled_for_value = payload.get("scheduled_for")
            return await self.send_publish_for_approval(
                tenant_id=tenant_id,
                content_job_id=request.content_job_id,
                platforms=list(cast(list[str], payload.get("platforms", []))),
                scheduled_for=datetime.fromisoformat(scheduled_for_value) if isinstance(scheduled_for_value, str) else None,
                recipient=request.recipient,
            )
        if request.approval_type == "topic" and request.related_entity_id:
            return await self.send_topic_for_approval(
                tenant_id=tenant_id,
                candidate_id=UUID(request.related_entity_id),
                recipient=request.recipient,
            )
        raise HTTPException(status_code=422, detail="Approval request type cannot be resent")

    async def operator_action(
        self,
        *,
        tenant_id: UUID,
        request_id: UUID,
        action: str,
        feedback: str | None,
        actor_user_id: UUID | None,
    ) -> ApprovalRequestResponse:
        request = await self.repo.get_request(tenant_id, request_id)
        if not request:
            raise HTTPException(status_code=404, detail="Approval request not found")
        normalized = action.lower()
        if normalized == "regenerate":
            if not request.content_job_id:
                raise HTTPException(status_code=422, detail="Regenerate is only supported for content-backed approvals")
            revised_job = await self.content_service.regenerate_with_feedback(
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
            await self._apply_intent(request, ApprovalIntent.APPROVE.value, feedback)
        elif normalized == "reject":
            await self._apply_intent(request, ApprovalIntent.REJECT.value, feedback)
        elif normalized == "revise":
            await self._apply_intent(request, ApprovalIntent.REVISE.value, feedback)
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported approval action '{action}'")
        request.responded_by = str(actor_user_id) if actor_user_id else "dashboard"
        request.responded_at = datetime.now(timezone.utc)
        await self.db.flush()
        return await self.get_request_detail(tenant_id, request.id)

    async def _apply_intent(
        self, request: ApprovalRequest, intent: str, feedback: str | None
    ) -> None:
        """Shared intent dispatch used by both WhatsApp and Telegram handlers."""
        max_revisions = 5
        if intent == ApprovalIntent.APPROVE.value:
            request.status = ApprovalStatus.APPROVED.value
            if request.content_job_id:
                await self._record_preference(request.tenant_id, request.content_job_id, "approve")
                if request.approval_type == "publish":
                    payload = request.response_payload_json or {}
                    scheduled_for_value = payload.get("scheduled_for")
                    await self.publish_service.publish_now(
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
                elif request.approval_type == "asset":
                    await self.publish_service.publish_now(
                        tenant_id=request.tenant_id,
                        approval_request_id=request.id,
                        payload=PublishNowRequest(content_job_id=request.content_job_id),
                    )
        elif intent == ApprovalIntent.REVISE.value and feedback:
            if request.revision_count >= max_revisions:
                request.status = ApprovalStatus.REJECTED.value
                return
            request.status = ApprovalStatus.REVISION_REQUESTED.value
            request.revision_count += 1
            if request.content_job_id:
                await self._record_preference(request.tenant_id, request.content_job_id, "revise")
                revised_job = await self.content_service.regenerate_with_feedback(
                    tenant_id=request.tenant_id,
                    job_id=request.content_job_id,
                    feedback=feedback,
                    requested_by_user_id=None,
                    source_channel=request.channel,
                )
                request.content_job_id = revised_job.id
                request.status = ApprovalStatus.PENDING.value
                await self.send_for_approval(
                    tenant_id=request.tenant_id,
                    content_job_id=revised_job.id,
                    recipient=request.recipient,
                )
        elif intent == ApprovalIntent.REJECT.value:
            request.status = ApprovalStatus.REJECTED.value
            if request.content_job_id:
                await self._record_preference(request.tenant_id, request.content_job_id, "reject")

    async def handle_telegram_callback(
        self,
        payload: dict[str, Any],
    ) -> None:
        await _handle_telegram_callback(self, payload)


    async def handle_telegram_message(self, payload: dict[str, Any]) -> bool:
        return await _handle_telegram_message(self, payload)

