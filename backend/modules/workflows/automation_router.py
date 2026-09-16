"""Automation HTTP routes (Phase 13)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.workflows.automation_schemas import (
    AutomationCreateRequest,
    AutomationResponse,
    AutomationUpdateRequest,
    BrandOptionResponse,
)
from backend.modules.workflows.automation_service import AutomationService

router = APIRouter()


@router.get("/brands", response_model=list[BrandOptionResponse])
async def list_workflow_brands(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[BrandOptionResponse]:
    return await AutomationService(db).list_brands(membership.tenant_id)


@router.get("/automations", response_model=list[AutomationResponse])
async def list_automations(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[AutomationResponse]:
    return await AutomationService(db).list_automations(membership.tenant_id)


@router.post("/automations", response_model=AutomationResponse, status_code=201)
async def create_automation(
    payload: AutomationCreateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> AutomationResponse:
    return await AutomationService(db).create_automation(
        membership.tenant_id, payload, actor_user_id=membership.user_id
    )


@router.get("/automations/{automation_id}", response_model=AutomationResponse)
async def get_automation(
    automation_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> AutomationResponse:
    row = await AutomationService(db).get_automation(membership.tenant_id, automation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return row


@router.patch("/automations/{automation_id}", response_model=AutomationResponse)
async def update_automation(
    automation_id: UUID,
    payload: AutomationUpdateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> AutomationResponse:
    return await AutomationService(db).update_automation(
        membership.tenant_id, automation_id, payload, actor_user_id=membership.user_id
    )
