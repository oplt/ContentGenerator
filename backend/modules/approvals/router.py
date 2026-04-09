from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.core.cache import redis_client
from backend.modules.approvals.schemas import ApprovalActionRequest, ApprovalRequestResponse, SendApprovalRequest
from backend.modules.approvals.service import ApprovalService
from backend.modules.identity_access.models import TenantUser
from backend.modules.settings.service import SettingsService

router = APIRouter()
_TELEGRAM_REPLAY_TTL_SECONDS = 600


async def _reserve_telegram_replay_key(payload: dict[str, object]) -> bool:
    replay_key = ""
    if payload.get("update_id") is not None:
        replay_key = f"telegram:update:{payload['update_id']}"
    else:
        callback_query = payload.get("callback_query")
        if isinstance(callback_query, dict) and callback_query.get("id"):
            replay_key = f"telegram:callback:{callback_query['id']}"
        else:
            message = payload.get("message")
            if isinstance(message, dict) and message.get("message_id"):
                chat = message.get("chat")
                if isinstance(chat, dict) and chat.get("id"):
                    replay_key = f"telegram:message:{chat['id']}:{message['message_id']}"
    if not replay_key:
        return True
    accepted = await redis_client.set(replay_key, "1", ex=_TELEGRAM_REPLAY_TTL_SECONDS, nx=True)
    return bool(accepted)


# ── Static webhook routes must come before /{request_id} ─────────────────────

@router.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = SettingsService(db)
    if hub_mode == "subscribe" and await service.verify_whatsapp_verify_token(hub_verify_token):
        return Response(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook", status_code=202)
async def receive_whatsapp_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from backend.workers.tasks import process_webhook_inbox_task
    raw_body = await request.body()
    payload = json.loads(raw_body.decode("utf-8"))
    service = ApprovalService(db)
    inbox_id = await service.handle_webhook(
        payload=payload,
        raw_body=raw_body,
        signature=x_hub_signature_256,
    )
    # Dispatch async processing — return 202 immediately to WhatsApp
    process_webhook_inbox_task.delay(inbox_id=inbox_id)
    return {"status": "accepted"}


@router.post("/telegram/webhook", status_code=200)
async def receive_telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    from backend.core.config import settings as _settings
    expected_secret = getattr(_settings, "TELEGRAM_WEBHOOK_SECRET", "")
    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret")

    payload = await request.json()
    if not await _reserve_telegram_replay_key(payload):
        return {"ok": True}
    service = ApprovalService(db)

    # Dispatch brief callbacks (gate 1) before content callbacks (gate 2)
    callback_query = payload.get("callback_query", {})
    if callback_query:
        callback_data = callback_query.get("data", "")
        if any(
            callback_data.startswith(prefix)
            for prefix in (
                "approve_brief:",
                "reject_brief:",
                "safer_brief:",
                "soften_brief:",
                "text_only_brief:",
                "text_video_brief:",
            )
        ):
            from backend.modules.editorial_briefs.service import EditorialBriefService
            brief_svc = EditorialBriefService(db)
            await brief_svc.handle_telegram_brief_callback(payload)
            return {"ok": True}

    # Plain-text messages may be revision follow-ups; check session first
    if "message" in payload and "callback_query" not in payload:
        consumed = await service.handle_telegram_message(payload)
        if consumed:
            return {"ok": True}
    # Otherwise handle as content approval inline button callback (gate 2)
    await service.handle_telegram_callback(payload)
    return {"ok": True}


# ── Authenticated approval routes ─────────────────────────────────────────────

@router.get("", response_model=list[ApprovalRequestResponse])
async def list_approval_requests(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequestResponse]:
    service = ApprovalService(db)
    requests = await service.list_requests(membership.tenant_id)
    return [await service.get_request_detail(membership.tenant_id, item.id) for item in requests]


@router.post("", response_model=ApprovalRequestResponse, status_code=201)
async def send_for_approval(
    payload: SendApprovalRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    service = ApprovalService(db)
    if payload.approval_type == "topic":
        if not payload.related_entity_id:
            raise HTTPException(status_code=422, detail="related_entity_id is required for topic approval")
        request_obj = await service.send_topic_for_approval(
            tenant_id=membership.tenant_id,
            candidate_id=UUID(payload.related_entity_id),
            recipient=payload.recipient,
        )
    elif payload.approval_type == "publish":
        if not payload.content_job_id:
            raise HTTPException(status_code=422, detail="content_job_id is required for publish approval")
        request_obj = await service.send_publish_for_approval(
            tenant_id=membership.tenant_id,
            content_job_id=payload.content_job_id,
            platforms=payload.selected_platforms,
            scheduled_for=payload.scheduled_for,
            recipient=payload.recipient,
        )
    else:
        if not payload.content_job_id:
            raise HTTPException(status_code=422, detail="content_job_id is required for asset approval")
        request_obj = await service.send_for_approval(
            tenant_id=membership.tenant_id,
            content_job_id=payload.content_job_id,
            recipient=payload.recipient,
        )
    await db.commit()
    return await service.get_request_detail(membership.tenant_id, request_obj.id)


@router.post("/{request_id}/resend", response_model=ApprovalRequestResponse)
async def resend_approval_request(
    request_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    service = ApprovalService(db)
    request_obj = await service.resend_request(membership.tenant_id, request_id)
    await db.commit()
    return await service.get_request_detail(membership.tenant_id, request_obj.id)


@router.post("/{request_id}/action", response_model=ApprovalRequestResponse)
async def action_approval_request(
    request_id: UUID,
    payload: ApprovalActionRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    service = ApprovalService(db)
    detail = await service.operator_action(
        tenant_id=membership.tenant_id,
        request_id=request_id,
        action=payload.action,
        feedback=payload.feedback,
        actor_user_id=membership.user_id,
    )
    await db.commit()
    return detail


@router.get("/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval_request(
    request_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    service = ApprovalService(db)
    return await service.get_request_detail(membership.tenant_id, request_id)
