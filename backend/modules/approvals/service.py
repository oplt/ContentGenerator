"""Approval service facade — delegates to focused collaborators."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals import approval_actions, approval_helpers, approval_outbound
from backend.modules.approvals.models import ApprovalRequest
from backend.modules.approvals.providers import TelegramProvider
from backend.modules.approvals.repository import ApprovalRepository
from backend.modules.approvals.schemas import ApprovalMessageResponse, ApprovalRequestResponse
from backend.modules.approvals.telegram_callbacks import (
    handle_telegram_callback as _handle_telegram_callback,
)
from backend.modules.approvals.telegram_messages import (
    handle_telegram_message as _handle_telegram_message,
)
from backend.modules.approvals.webhook_processing import (
    handle_webhook as _handle_webhook,
    process_webhook_inbox as _process_webhook_inbox,
)
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.publishing.service import PublishingService
from backend.modules.settings.service import SettingsService
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository

__all__ = ["ApprovalService"]


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
        return approval_helpers.risk_payload_for_job(content_job)

    @staticmethod
    def _extract_phone_number_id(payload: dict[str, Any]) -> str | None:
        return approval_helpers.extract_phone_number_id(payload)

    async def _build_summary_text(
        self, tenant_id: UUID, content_job_id: UUID, approval_request_id: UUID
    ) -> str:
        return await approval_helpers.build_summary_text(
            self, tenant_id, content_job_id, approval_request_id
        )

    async def _build_telegram_asset_previews(
        self, tenant_id: UUID, content_job_id: UUID
    ) -> tuple[str, list[str]]:
        return await approval_helpers.build_telegram_asset_previews(
            self, tenant_id, content_job_id
        )

    async def _telegram_runtime(
        self, tenant_id: UUID
    ) -> tuple[dict[str, str | bool], TelegramProvider | None]:
        return await approval_helpers.telegram_runtime(self, tenant_id)

    async def _create_or_refresh_request(self, **kwargs: Any) -> ApprovalRequest:
        return await approval_helpers.create_or_refresh_request(self, **kwargs)

    async def send_for_approval(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        recipient: str | None,
        channels: list[str] | None = None,
        deliver: bool = True,
    ) -> ApprovalRequest:
        return await approval_outbound.send_for_approval(
            self,
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            recipient=recipient,
            channels=channels,
            deliver=deliver,
        )

    async def send_topic_for_approval(
        self,
        *,
        tenant_id: UUID,
        candidate_id: UUID,
        recipient: str | None = None,
    ) -> ApprovalRequest:
        return await approval_outbound.send_topic_for_approval(
            self,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            recipient=recipient,
        )

    async def send_publish_for_approval(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        platforms: list[str],
        scheduled_for: datetime | None = None,
        recipient: str | None = None,
    ) -> ApprovalRequest:
        return await approval_outbound.send_publish_for_approval(
            self,
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            platforms=platforms,
            scheduled_for=scheduled_for,
            recipient=recipient,
        )

    async def list_requests(self, tenant_id: UUID) -> list[ApprovalRequest]:
        return await self.repo.list_requests(tenant_id)

    async def get_request_detail(
        self, tenant_id: UUID, request_id: UUID
    ) -> ApprovalRequestResponse:
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
            risk_label=(
                str(request.response_payload_json.get("risk_label"))
                if request.response_payload_json.get("risk_label")
                else None
            ),
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
        await approval_actions.record_preference(self, tenant_id, content_job_id, outcome)

    async def _record_callback_failure(
        self,
        request: ApprovalRequest | None,
        *,
        callback_data: str,
        reason: str,
    ) -> None:
        await approval_actions.record_callback_failure(
            self, request, callback_data=callback_data, reason=reason
        )

    async def resend_request(self, tenant_id: UUID, request_id: UUID) -> ApprovalRequest:
        return await approval_actions.resend_request(self, tenant_id, request_id)

    async def operator_action(
        self,
        *,
        tenant_id: UUID,
        request_id: UUID,
        action: str,
        feedback: str | None,
        actor_user_id: UUID | None,
    ) -> ApprovalRequestResponse:
        return await approval_actions.operator_action(
            self,
            tenant_id=tenant_id,
            request_id=request_id,
            action=action,
            feedback=feedback,
            actor_user_id=actor_user_id,
        )

    async def _apply_intent(
        self, request: ApprovalRequest, intent: str, feedback: str | None
    ) -> None:
        await approval_actions.apply_intent(self, request, intent, feedback)

    async def handle_telegram_callback(self, payload: dict[str, Any]) -> None:
        await _handle_telegram_callback(self, payload)

    async def handle_telegram_message(self, payload: dict[str, Any]) -> bool:
        return await _handle_telegram_message(self, payload)
