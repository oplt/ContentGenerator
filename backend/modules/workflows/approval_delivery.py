"""Channel-aware approval delivery (Phase 9).

Creates the ApprovalRequest via ApprovalService helpers, then delivers to the
configured channels only — never invents telegram/whatsapp when not requested.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from backend.core.config import settings
from backend.modules.approvals.approval_helpers import (
    build_summary_text,
    build_telegram_asset_previews,
    telegram_runtime,
)
from backend.modules.approvals.models import ApprovalIntent, ApprovalMessage, ApprovalRequest
from backend.modules.approvals.providers import get_whatsapp_provider


class ApprovalDeliveryService:
    """Deliver an existing ApprovalRequest across configured channels."""

    async def deliver(
        self,
        svc: Any,
        request: ApprovalRequest,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        channels: list[str],
    ) -> list[str]:
        """Send outbound notifications for each channel. Returns delivered names."""
        delivered: list[str] = []
        normalized = [str(c).strip().lower() for c in channels if str(c).strip()]
        if not normalized:
            normalized = ["in_app"]

        for channel in normalized:
            if channel == "in_app":
                delivered.append("in_app")
                continue
            if channel == "telegram":
                if await self._deliver_telegram(
                    svc, request, tenant_id=tenant_id, content_job_id=content_job_id
                ):
                    delivered.append("telegram")
                continue
            if channel in {"whatsapp", "wa"}:
                if await self._deliver_whatsapp(
                    svc, request, tenant_id=tenant_id, content_job_id=content_job_id
                ):
                    delivered.append("whatsapp")
                continue
        return delivered

    async def _deliver_telegram(
        self,
        svc: Any,
        request: ApprovalRequest,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
    ) -> bool:
        _telegram_config, telegram = await telegram_runtime(svc, tenant_id)
        if not telegram:
            return False
        from backend.modules.approvals.approval_helpers import risk_payload_for_job

        content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
        risk_payload = risk_payload_for_job(content_job) if content_job else {"risk_label": "unknown"}
        headline, platform_previews = await build_telegram_asset_previews(
            svc, tenant_id, content_job_id
        )
        tg_result = await telegram.send_asset_card(
            headline=headline,
            platform_previews=platform_previews,
            approval_request_id=str(request.id),
            risk_level=str(risk_payload.get("risk_label", "unknown")),
        )
        request.provider_request_id = tg_result.get("message_id")
        request.telegram_message_id = tg_result.get("message_id")
        request.channel = "telegram"
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
        return True

    async def _deliver_whatsapp(
        self,
        svc: Any,
        request: ApprovalRequest,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
    ) -> bool:
        runtime_config = await svc.settings_service.resolve_whatsapp_runtime_config(tenant_id)
        if not (request.recipient or runtime_config.recipient or settings.WHATSAPP_DEFAULT_RECIPIENT):
            return False
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
        return True
