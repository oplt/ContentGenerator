from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.approvals.schemas import ApprovalRequestResponse, SendApprovalRequest
from backend.modules.approvals.service import ApprovalService
from backend.modules.identity_access.models import TenantUser
from backend.modules.settings.service import SettingsService

router = APIRouter()


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
    service = ApprovalService(db)
    # Plain-text messages may be revision follow-ups; check session first
    if "message" in payload and "callback_query" not in payload:
        consumed = await service.handle_telegram_message(payload)
        if consumed:
            return {"ok": True}
    # Otherwise handle as inline button callback
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
    request_obj = await service.send_for_approval(
        tenant_id=membership.tenant_id,
        content_job_id=payload.content_job_id,
        recipient=payload.recipient,
    )
    await db.commit()
    return await service.get_request_detail(membership.tenant_id, request_obj.id)


@router.get("/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval_request(
    request_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    service = ApprovalService(db)
    return await service.get_request_detail(membership.tenant_id, request_id)
