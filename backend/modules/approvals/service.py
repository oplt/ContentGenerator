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
from backend.modules.approvals.providers import TelegramProvider, WhatsAppRuntimeConfig, get_whatsapp_provider
from backend.modules.approvals.repository import ApprovalRepository
from backend.modules.approvals.schemas import ApprovalMessageResponse, ApprovalRequestResponse
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.publishing.schemas import PublishNowRequest
from backend.modules.publishing.service import PublishingService
from backend.modules.settings.service import SettingsService


class ApprovalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ApprovalRepository(db)
        self.content_repo = ContentGenerationRepository(db)
        self.content_service = ContentGenerationService(db)
        self.publish_service = PublishingService(db)
        self.settings_service = SettingsService(db)
        self.audit = AuditService(db)

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

    async def send_for_approval(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        recipient: str | None,
    ) -> ApprovalRequest:
        runtime_config = await self.settings_service.resolve_whatsapp_runtime_config(tenant_id)
        provider = get_whatsapp_provider(runtime_config)
        resolved_recipient = (
            (recipient or runtime_config.recipient or settings.WHATSAPP_DEFAULT_RECIPIENT).strip()
        )
        if not resolved_recipient:
            raise HTTPException(
                status_code=400,
                detail="No WhatsApp recipient configured for this tenant",
            )
        existing = await self.repo.get_request_for_content_job(content_job_id)
        request = existing
        if not request:
            request = await self.repo.create_request(
                ApprovalRequest(
                    tenant_id=tenant_id,
                    content_job_id=content_job_id,
                    status=ApprovalStatus.PENDING.value,
                    channel="whatsapp",
                    recipient=resolved_recipient,
                    provider=runtime_config.provider,
                    requested_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(days=2),
                )
            )
        elif request.recipient != resolved_recipient:
            request.recipient = resolved_recipient
        message_text = await self._build_summary_text(tenant_id, content_job_id, request.id)
        send_result = await provider.send_message(to=request.recipient, text=message_text)
        request.provider_request_id = send_result.get("message_id")
        request.last_sent_at = datetime.now(timezone.utc)
        request.status = ApprovalStatus.PENDING.value
        request.provider = runtime_config.provider
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
        # Also send via Telegram if configured and enabled
        telegram_config = await self.settings_service.resolve_telegram_runtime_config(tenant_id)
        if telegram_config.get("enabled") and telegram_config.get("bot_token") and telegram_config.get("chat_id"):
            telegram = TelegramProvider(
                bot_token=str(telegram_config["bot_token"]),
                chat_id=str(telegram_config["chat_id"]),
            )
            try:
                tg_result = await telegram.send_message(message_text, approval_request_id=str(request.id))
                await self.repo.create_message(
                    ApprovalMessage(
                        approval_request_id=request.id,
                        direction="outbound",
                        channel="telegram",
                        provider_message_id=tg_result.get("message_id"),
                        message_type="text",
                        raw_text=message_text,
                        parsed_intent=ApprovalIntent.UNKNOWN.value,
                        intent_confidence=1.0,
                        payload=tg_result,
                    )
                )
            except Exception:
                pass  # Telegram failure must not block the approval request

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="approvals.request_sent",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Approval request sent",
            payload={"content_job_id": str(content_job_id), "recipient": request.recipient},
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

    async def _apply_intent(
        self, request: ApprovalRequest, intent: str, feedback: str | None
    ) -> None:
        """Shared intent dispatch used by both WhatsApp and Telegram handlers."""
        max_revisions = 5
        if intent == ApprovalIntent.APPROVE.value:
            request.status = ApprovalStatus.APPROVED.value
            await self._record_preference(request.tenant_id, request.content_job_id, "approve")
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
            await self._record_preference(request.tenant_id, request.content_job_id, "reject")

    async def handle_telegram_callback(
        self,
        payload: dict,
    ) -> None:
        """Process an inline keyboard callback_query from Telegram."""
        callback_query = payload.get("callback_query")
        if not callback_query:
            return

        callback_query_id = callback_query.get("id", "")
        data = callback_query.get("data", "")
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
        # data format: "approve:<uuid>" | "reject:<uuid>" | "revise:<uuid>"
        parts = data.split(":", 1)
        if len(parts) != 2:
            return
        intent_str, request_id_str = parts

        # Resolve the approval request across all tenants
        try:
            request_uuid = UUID(request_id_str)
        except ValueError:
            return
        request = await self.repo.get_request_by_id(request_uuid)
        if not request:
            return

        try:
            telegram_config = await self.settings_service.resolve_telegram_runtime_config(request.tenant_id)
            bot_token = str(telegram_config.get("bot_token", ""))
            chat_id = str(telegram_config.get("chat_id", ""))
        except Exception:
            bot_token = ""
            chat_id = ""

        if intent_str == "approve":
            request.responded_at = datetime.now(timezone.utc)
            ack_text = "✅ Content approved and queued for publishing."
            try:
                await self._apply_intent(request, ApprovalIntent.APPROVE.value, None)
            except Exception:
                ack_text = "✅ Approved — publishing could not be queued (check platform settings)."
        elif intent_str == "reject":
            request.responded_at = datetime.now(timezone.utc)
            await self._apply_intent(request, ApprovalIntent.REJECT.value, None)
            ack_text = "❌ Content rejected."
        elif intent_str == "revise":
            # Set a Redis session so the next plain-text message from this chat is treated as revision feedback
            if chat_id:
                await redis_client.setex(
                    f"approval:pending_revision:{chat_id}",
                    600,  # 10-minute window
                    str(request.id),
                )
            request.status = ApprovalStatus.PENDING.value
            ack_text = "✏️ Send your revision notes as a reply in this chat (10 min window)."
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
                payload={"callback_data": data},
            )
        )

        if bot_token and callback_query_id:
            try:
                from backend.modules.approvals.providers import TelegramProvider
                provider = TelegramProvider(bot_token=bot_token, chat_id=chat_id)
                await provider.answer_callback(callback_query_id, ack_text)
            except Exception:
                pass  # Ack failure must not roll back the approval state change

        await self.audit.record(
            tenant_id=request.tenant_id,
            actor_user_id=None,
            action="approvals.telegram_callback",
            entity_type="approval_request",
            entity_id=str(request.id),
            message=f"Telegram callback: {intent_str}",
            payload={"intent": intent_str},
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
            payload={"feedback_length": str(len(text))},
        )
        await self.db.commit()
        return True
