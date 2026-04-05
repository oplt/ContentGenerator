from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.analytics.schemas import AnalyticsOverviewResponse
from backend.modules.analytics.service import AnalyticsService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.post("/sync", status_code=202)
async def sync_analytics(
    membership: TenantUser = Depends(require_permission("analytics:read")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    service = AnalyticsService(db)
    snapshots = await service.sync_snapshots(membership.tenant_id)
    await db.commit()
    return {"snapshots": len(snapshots)}


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverviewResponse:
    service = AnalyticsService(db)
    return await service.overview(membership.tenant_id)
