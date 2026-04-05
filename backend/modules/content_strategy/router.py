from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.content_strategy.schemas import (
    BrandProfileResponse,
    BrandProfileUpsertRequest,
    ContentPlanResponse,
    CreateContentPlanRequest,
)
from backend.modules.content_strategy.service import ContentStrategyService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.get("/brand-profile", response_model=BrandProfileResponse)
async def get_brand_profile(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> BrandProfileResponse:
    service = ContentStrategyService(db)
    profile = await service.get_or_create_brand_profile(membership.tenant_id)
    await db.commit()
    return BrandProfileResponse.model_validate(profile)


@router.put("/brand-profile", response_model=BrandProfileResponse)
async def upsert_brand_profile(
    payload: BrandProfileUpsertRequest,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> BrandProfileResponse:
    service = ContentStrategyService(db)
    profile = await service.upsert_brand_profile(membership.tenant_id, payload)
    await db.commit()
    return BrandProfileResponse.model_validate(profile)


@router.get("/plans", response_model=list[ContentPlanResponse])
async def list_content_plans(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ContentPlanResponse]:
    service = ContentStrategyService(db)
    plans = await service.list_content_plans(membership.tenant_id)
    return [ContentPlanResponse.model_validate(plan) for plan in plans]


@router.get("/plans/{plan_id}", response_model=ContentPlanResponse)
async def get_content_plan(
    plan_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ContentPlanResponse:
    service = ContentStrategyService(db)
    return ContentPlanResponse.model_validate(
        await service.get_content_plan(membership.tenant_id, plan_id)
    )


@router.post("/plans", response_model=ContentPlanResponse, status_code=201)
async def create_content_plan(
    payload: CreateContentPlanRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ContentPlanResponse:
    service = ContentStrategyService(db)
    plan = await service.create_plan_for_cluster(
        tenant_id=membership.tenant_id,
        cluster_id=payload.story_cluster_id,
        brand_profile_id=payload.brand_profile_id,
    )
    await db.commit()
    return ContentPlanResponse.model_validate(plan)
