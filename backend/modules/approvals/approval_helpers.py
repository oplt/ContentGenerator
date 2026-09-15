from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from backend.modules.approvals.models import ApprovalRequest, ApprovalStatus
from backend.modules.approvals.providers import TelegramProvider, get_telegram_provider


def risk_payload_for_job(content_job: Any) -> dict[str, object]:
    grounding = content_job.grounding_bundle if isinstance(getattr(content_job, "grounding_bundle", None), dict) else {}
    review = grounding.get("risk_review", {})
    if not isinstance(review, dict):
        review = {}
    return {
        "risk_label": str(review.get("label") or grounding.get("risk_label") or "low"),
        "risk_review": review,
    }


def extract_phone_number_id(payload: dict[str, Any]) -> str | None:
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            metadata = change.get("value", {}).get("metadata", {})
            phone_number_id = metadata.get("phone_number_id")
            if phone_number_id:
                return str(phone_number_id)
    return None


async def build_summary_text(
    svc, tenant_id: UUID, content_job_id: UUID, approval_request_id: UUID) -> str:
    content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
    if not content_job:
        raise HTTPException(status_code=404, detail="Content job not found")
    assets = await svc.content_repo.list_assets(content_job.id)
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


async def build_telegram_asset_previews(
    svc, tenant_id: UUID, content_job_id: UUID) -> tuple[str, list[str]]:
    """Returns (headline, list_of_platform_preview_strings) for the Telegram asset card."""
    content_job = await svc.content_repo.get_job(tenant_id, content_job_id)
    headline = (
        str(content_job.grounding_bundle.get("headline", "Content ready for review"))
        if content_job
        else "Content ready for review"
    )
    if not content_job:
        return headline, []
    assets = await svc.content_repo.list_assets(content_job.id)
    text_variants = [a for a in assets if a.asset_type == "text_variant"]
    previews = [f"[{(a.platform or 'UNKNOWN').upper()}] {(a.text_content or '')[:200]}" for a in text_variants[:3]]
    return headline, previews


async def telegram_runtime(
    svc, tenant_id: UUID) -> tuple[dict[str, str | bool], TelegramProvider | None]:
    telegram_config = await svc.settings_service.resolve_telegram_runtime_config(tenant_id)
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


async def create_or_refresh_request(
    svc,
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
        request = await svc.repo.get_request_for_content_job(content_job_id)
    elif related_entity_type and related_entity_id:
        request = await svc.repo.get_request_for_related_entity(
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
        await svc.db.flush()
        return request
    return await svc.repo.create_request(
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


