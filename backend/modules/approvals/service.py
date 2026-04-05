from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage, ApprovalRequest, ApprovalStatus, WebhookInbox
from backend.modules.approvals.providers import WhatsAppRuntimeConfig, get_whatsapp_provider
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
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="approvals.request_sent",
            entity_type="approval_request",
            entity_id=str(request.id),
            message="Approval request sent over WhatsApp",
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
    ) -> list[ApprovalRequest]:
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
            # Reject messages with invalid signatures when a secret is configured.
            # In stub/dev mode WHATSAPP_APP_SECRET is empty, so we allow through.
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        dedupe_key = hashlib.sha256(raw_body).hexdigest()
        existing_webhook = await self.repo.get_webhook_by_dedupe_key(dedupe_key)
        if existing_webhook:
            return []  # Idempotent: already processed
        await self.repo.create_webhook(
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
        updated_requests: list[ApprovalRequest] = []
        for parsed in provider.parse_payload(payload):
            request_id = parsed.approval_request_id
            if request_id is None:
                text_parts = parsed.raw_text.split()
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
                    payload={"raw_text": parsed.raw_text},
                )
            )
            request.responded_at = datetime.now(timezone.utc)

            if parsed.intent == ApprovalIntent.APPROVE.value:
                request.status = ApprovalStatus.APPROVED.value
                await self.publish_service.publish_now(
                    tenant_id=request.tenant_id,
                    approval_request_id=request.id,
                    payload=PublishNowRequest(content_job_id=request.content_job_id),
                )
            elif parsed.intent == ApprovalIntent.REVISE.value and parsed.feedback:
                request.status = ApprovalStatus.REVISION_REQUESTED.value
                request.revision_count += 1
                revised_job = await self.content_service.regenerate_with_feedback(
                    tenant_id=request.tenant_id,
                    job_id=request.content_job_id,
                    feedback=parsed.feedback,
                    requested_by_user_id=None,
                    source_channel="whatsapp",
                )
                request.content_job_id = revised_job.id
                request.status = ApprovalStatus.PENDING.value
                await self.send_for_approval(
                    tenant_id=request.tenant_id,
                    content_job_id=revised_job.id,
                    recipient=request.recipient,
                )
            elif parsed.intent == ApprovalIntent.REJECT.value:
                request.status = ApprovalStatus.REJECTED.value

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
        await self.db.flush()
        return updated_requests
