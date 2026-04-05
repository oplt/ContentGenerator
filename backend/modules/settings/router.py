from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.settings.schemas import (
    TenantSettingsRequest,
    TenantSettingsResponse,
    WhatsAppSettingsRequest,
    WhatsAppSettingsResponse,
)
from backend.modules.settings.service import SettingsService

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
