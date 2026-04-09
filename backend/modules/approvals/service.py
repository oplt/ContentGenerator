from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
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
    def _risk_payload_for_job(content_job) -> dict[str, object]:
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
        headline = content_job.grounding_bundle.get("headline", "Content ready for review") if content_job else "Content ready for review"
        if not content_job:
            return headline, []
        assets = await self.content_repo.list_assets(content_job.id)
        text_variants = [a for a in assets if a.asset_type == "text_variant"]
        previews = [
            f"[{a.platform.upper()}] {(a.text_content or '')[:200]}"
            for a in text_variants[:3]
        ]
        return headline, previews

    async def _telegram_runtime(self, tenant_id: UUID) -> tuple[dict[str, str | bool], object | None]:
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
        tg_result = await telegram.send_topic_card(
            title=candidate.primary_topic,
            score=candidate.final_score,
            why_now=str(candidate.score_explanation.get("cluster_explainability", {}).get("why_now", "Emerging trend")),
            evidence_links=candidate.evidence_links,
            risk_level=str(candidate.score_explanation.get("review_risk_label", candidate.score_explanation.get("risk_level", "safe"))),
            callback_id=str(request.id),
        )
        request.response_payload_json = {
            **request.response_payload_json,
            "risk_label": str(candidate.score_explanation.get("review_risk_label", "low")),
            "topic_categories": candidate.score_explanation.get("topic_categories", []),
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
        headline = content_job.grounding_bundle.get("headline", "Ready to publish") if content_job else "Ready to publish"
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
            **{
                "id": request.id,
                "content_job_id": request.content_job_id,
                "status": str(request.status),
                "channel": request.channel,
                "recipient": request.recipient,
                "provider": request.provider,
                "provider_request_id": request.provider_request_id,
                "requested_at": request.requested_at,
                "responded_at": request.responded_at,
                "revision_count": request.revision_count,
                "expires_at": request.expires_at,
                "last_sent_at": request.last_sent_at,
                "related_entity_type": request.related_entity_type,
                "related_entity_id": request.related_entity_id,
                "approval_type": request.approval_type,
                "buttons_json": request.buttons_json,
                "telegram_message_id": request.telegram_message_id,
                "callback_verification_failures": request.callback_verification_failures,
                "callback_last_error": request.callback_last_error,
                "responded_by": request.responded_by,
                "risk_label": str(request.response_payload_json.get("risk_label")) if request.response_payload_json.get("risk_label") else None,
                "response_payload_json": request.response_payload_json,
                "messages": [ApprovalMessageResponse.model_validate(message) for message in messages],
            }
        )

    async def handle_webhook(
        self,
        *,
        payload: dict[str, Any],
        raw_body: bytes,
        signature: str | None,
    ) -> str:
        """
        Fast path: verify signature, write to WebhookInbox, return immediately.
        The actual intent processing is done asynchronously by process_webhook_inbox_task.
        """
        tenant_phone_number_id = self._extract_phone_number_id(payload)
        resolved_tenant_id: UUID | None = None
        runtime_config: WhatsAppRuntimeConfig | None = None
        if tenant_phone_number_id:
            resolved_tenant_id = await self.settings_service.find_tenant_id_by_whatsapp_phone_number_id(
                tenant_phone_number_id
            )
            if resolved_tenant_id:
                runtime_config = await self.settings_service.resolve_whatsapp_runtime_config(
                    resolved_tenant_id
                )
        if runtime_config is None:
            runtime_config = self.settings_service._global_whatsapp_runtime_config()
        provider = get_whatsapp_provider(runtime_config)

        signature_valid = provider.verify_signature(body=raw_body, signature=signature)
        if not signature_valid and runtime_config.app_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

        dedupe_key = hashlib.sha256(raw_body).hexdigest()
        existing_webhook = await self.repo.get_webhook_by_dedupe_key(dedupe_key)
        if existing_webhook:
            return str(existing_webhook.id)  # Idempotent

        inbox = await self.repo.create_webhook(
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
        await self.db.commit()
        return str(inbox.id)

    async def process_webhook_inbox(self, inbox_id: UUID) -> list[ApprovalRequest]:
        """
        Called by Celery. Processes a single WebhookInbox row: parses intent and acts.
        """
        inbox = await self.repo.get_pending_webhook(inbox_id)
        if not inbox or inbox.status != "received":
            return []

        raw_payload_str = inbox.payload.get("raw", "")
        import json as _json
        try:
            payload = _json.loads(raw_payload_str)
        except Exception:
            inbox.status = "error"
            inbox.error_message = "JSON parse failed"
            await self.db.commit()
            return []

        runtime_config: WhatsAppRuntimeConfig | None = None
        if inbox.tenant_id:
            runtime_config = await self.settings_service.resolve_whatsapp_runtime_config(inbox.tenant_id)
        if runtime_config is None:
            runtime_config = self.settings_service._global_whatsapp_runtime_config()
        provider = get_whatsapp_provider(runtime_config)

        inbox.status = "processing"
        await self.db.flush()

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
                request = await self.repo.get_request_by_id(request_id)
                if request is None:
                    continue

                await self.repo.create_message(
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
                await self._apply_intent(request, parsed.intent, parsed.feedback)
                await self.audit.record(
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
            await self.db.commit()
            raise

        inbox.status = "processed"
        inbox.processed_at = datetime.now(timezone.utc)
        await self.db.commit()
        return updated_requests

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
            prefs: dict = {}
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
            return await self.send_for_approval(
                tenant_id=tenant_id,
                content_job_id=request.content_job_id,
                recipient=request.recipient,
            )
        if request.approval_type == "publish":
            payload = request.response_payload_json or {}
            return await self.send_publish_for_approval(
                tenant_id=tenant_id,
                content_job_id=request.content_job_id,
                platforms=list(payload.get("platforms", [])),
                scheduled_for=datetime.fromisoformat(payload["scheduled_for"]) if payload.get("scheduled_for") else None,
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
                    await self.publish_service.publish_now(
                        tenant_id=request.tenant_id,
                        approval_request_id=request.id,
                        payload=PublishNowRequest(
                            content_job_id=request.content_job_id,
                            platforms=list(payload.get("platforms", [])) or None,
                            scheduled_for=datetime.fromisoformat(payload["scheduled_for"]) if payload.get("scheduled_for") else None,
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
        payload: dict,
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
            request = await self.repo.get_request_by_id(request_uuid)
        except ValueError:
            request_uuid = None
        if not is_valid:
            await self._record_callback_failure(request, callback_data=data, reason="invalid_signature")
            await self.db.commit()
            return

        if not request:
            return

        try:
            telegram_config = await self.settings_service.resolve_telegram_runtime_config(request.tenant_id)
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
                candidate = await self.story_repo.get_trend_candidate(request.tenant_id, UUID(request.related_entity_id))
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
                    await self._apply_intent(request, ApprovalIntent.APPROVE.value, None)
                    if request.approval_type == "asset" and request.content_job_id:
                        content_job = await self.content_repo.get_job(request.tenant_id, request.content_job_id)
                        if content_job:
                            plan = await self.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
                            if plan:
                                cluster = await self.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
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
                candidate = await self.story_repo.get_trend_candidate(request.tenant_id, UUID(request.related_entity_id))
                if candidate:
                    candidate.status = TrendCandidateStatus.REJECTED_TOPIC.value
                request.status = ApprovalStatus.REJECTED.value
                request.response_payload_json = {"decision": "rejected_topic"}
                ack_text = "❌ Topic rejected."
                edited_text = "📡 Topic Approval — ❌ <b>REJECTED</b>."
            else:
                await self._apply_intent(request, ApprovalIntent.REJECT.value, None)
                if request.content_job_id:
                    content_job = await self.content_repo.get_job(request.tenant_id, request.content_job_id)
                    if content_job:
                        plan = await self.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
                        if plan:
                            cluster = await self.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
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
            content_job = await self.content_repo.get_job(request.tenant_id, request.content_job_id)
            if content_job:
                plan = await self.content_service.plan_repo.get_content_plan(request.tenant_id, content_job.content_plan_id)
                if plan:
                    cluster = await self.story_repo.get_cluster(request.tenant_id, plan.story_cluster_id)
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
            assets = await self.content_repo.list_assets(request.content_job_id)
            platforms = sorted({asset.platform for asset in assets if asset.platform})
            publish_request = await self.send_publish_for_approval(
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
            await self._apply_intent(request, ApprovalIntent.APPROVE.value, None)
            ack_text = f"✅ Publish approved for {platform}."
            edited_text = f"🚀 Publish Approval — ✅ <b>{platform.upper()} APPROVED</b>."
        elif intent_str in {"safer_topic", "regen_topic"}:
            request.status = ApprovalStatus.REVISION_REQUESTED.value
            request.response_payload_json = {"decision": intent_str}
            ack_text = "♻️ Topic routed for safer brief regeneration."
            edited_text = "📡 Topic Approval — ♻️ <b>SAFER BRIEF REQUESTED</b>."
        else:
            return

        await self.repo.create_message(
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

        await self.audit.record(
            tenant_id=request.tenant_id,
            actor_user_id=None,
            action="approvals.telegram_callback",
            entity_type="approval_request",
            entity_id=str(request.id),
            message=f"Telegram callback: {intent_str}",
            payload={"intent": intent_str, "approval_type": request.approval_type},
            payload_schema="approval.telegram_callback.v1",
        )
        await self.db.commit()

    async def handle_telegram_message(self, payload: dict) -> bool:
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
        request = await self.repo.get_request_by_id(request_id)
        if request is None:
            return False

        request.responded_at = datetime.now(timezone.utc)
        request.responded_by = f"telegram:{chat_id}"
        await self._apply_intent(request, ApprovalIntent.REVISE.value, text)
        await self.repo.create_message(
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
        await self.audit.record(
            tenant_id=request.tenant_id,
            actor_user_id=None,
            action="approvals.telegram_revision",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Telegram revision feedback received",
            payload={"feedback_length": len(text)},
            payload_schema="approval.telegram_revision.v1",
        )
        await self.db.commit()
        return True
