from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.settings.schemas import (
    TelegramSettingsRequest,
    TelegramSettingsResponse,
    TenantSettingsRequest,
    TenantSettingsResponse,
    WhatsAppSettingsRequest,
    WhatsAppSettingsResponse,
)
from backend.modules.settings.service import SettingsService
from backend.core.config import settings

router = APIRouter()


@router.get("/tenant", response_model=TenantSettingsResponse)
async def get_tenant_settings(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> TenantSettingsResponse:
    service = SettingsService(db)
    tenant = await service.get_tenant_settings(membership.tenant_id)
    return TenantSettingsResponse.model_validate(tenant)


@router.put("/tenant", response_model=TenantSettingsResponse)
async def update_tenant_settings(
    payload: TenantSettingsRequest,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> TenantSettingsResponse:
    service = SettingsService(db)
    tenant = await service.update_tenant_settings(membership.tenant_id, payload)
    await db.commit()
    return TenantSettingsResponse.model_validate(tenant)


@router.get("/whatsapp", response_model=WhatsAppSettingsResponse)
async def get_whatsapp_settings(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppSettingsResponse:
    service = SettingsService(db)
    return await service.get_whatsapp_settings(membership.tenant_id)


@router.put("/whatsapp", response_model=WhatsAppSettingsResponse)
async def update_whatsapp_settings(
    payload: WhatsAppSettingsRequest,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppSettingsResponse:
    service = SettingsService(db)
    result = await service.update_whatsapp_settings(membership.tenant_id, payload)
    await db.commit()
    return result


@router.get("/telegram", response_model=TelegramSettingsResponse)
async def get_telegram_settings(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> TelegramSettingsResponse:
    service = SettingsService(db)
    return await service.get_telegram_settings(membership.tenant_id)


@router.put("/telegram", response_model=TelegramSettingsResponse)
async def update_telegram_settings(
    payload: TelegramSettingsRequest,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> TelegramSettingsResponse:
    service = SettingsService(db)
    result = await service.update_telegram_settings(membership.tenant_id, payload)
    await db.commit()
    return result


@router.post("/telegram/register-webhook")
async def register_telegram_webhook(
        request: Request,
        membership: TenantUser = Depends(require_permission("settings:write")),
        db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    from backend.modules.approvals.providers import TelegramProvider
    import os

    service = SettingsService(db)
    config = await service.resolve_telegram_runtime_config(membership.tenant_id)
    if not config.get("bot_token"):
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")

    # Use environment variable for public URL, fall back to request base URL
    webhook_url = f"{settings.PUBLIC_URL}/api/v1/approvals/telegram/webhook"

    provider = TelegramProvider(bot_token=str(config["bot_token"]), chat_id=str(config.get("chat_id", "")))
    result = await provider.set_webhook(webhook_url)
    return {"webhook_url": webhook_url, "telegram_response": result}
