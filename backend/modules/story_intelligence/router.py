from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.story_intelligence.schemas import (
    StoryClusterDetailResponse,
    StoryClusterResponse,
    TrendCandidateActionRequest,
    TrendCandidateResponse,
    TrendDashboardResponse,
)
from backend.modules.story_intelligence.service import StoryIntelligenceService

router = APIRouter()


@router.get("/clusters", response_model=list[StoryClusterResponse])
async def list_clusters(
    worthy_only: bool = Query(default=False),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[StoryClusterResponse]:
    service = StoryIntelligenceService(db)
    return await service.list_clusters(tenant_id=membership.tenant_id, worthy_only=worthy_only)


@router.get("/clusters/{cluster_id}", response_model=StoryClusterDetailResponse)
async def get_cluster_detail(
    cluster_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> StoryClusterDetailResponse:
    service = StoryIntelligenceService(db)
    detail = await service.get_cluster_detail(tenant_id=membership.tenant_id, cluster_id=cluster_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Story cluster not found")
    return detail


@router.get("/candidates", response_model=list[TrendCandidateResponse])
async def list_trend_candidates(
    status: str | None = Query(default=None),
    brand_profile_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[TrendCandidateResponse]:
    service = StoryIntelligenceService(db)
    return await service.list_trend_candidates(
        tenant_id=membership.tenant_id,
        status=status,
        brand_profile_id=brand_profile_id,
        limit=limit,
    )


@router.get("/candidates/{candidate_id}", response_model=TrendCandidateResponse)
async def get_trend_candidate_detail(
    candidate_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> TrendCandidateResponse:
    service = StoryIntelligenceService(db)
    detail = await service.get_trend_candidate_detail(tenant_id=membership.tenant_id, candidate_id=candidate_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Trend candidate not found")
    return detail


@router.post("/candidates/{candidate_id}/action", response_model=TrendCandidateResponse)
async def action_trend_candidate(
    candidate_id: UUID,
    payload: TrendCandidateActionRequest,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> TrendCandidateResponse:
    service = StoryIntelligenceService(db)
    try:
        detail = await service.apply_candidate_action(
            tenant_id=membership.tenant_id,
            candidate_id=candidate_id,
            action=payload.action,
            operator_note=payload.operator_note,
        )
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return detail


@router.get("/trends/dashboard", response_model=TrendDashboardResponse)
async def get_trend_dashboard(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> TrendDashboardResponse:
    service = StoryIntelligenceService(db)
    return await service.trend_dashboard(tenant_id=membership.tenant_id)
