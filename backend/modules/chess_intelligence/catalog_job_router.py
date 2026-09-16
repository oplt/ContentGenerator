"""Chess catalog async job API — `/api/v1/chess/jobs`."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import require_permission
from backend.api.deps.db import get_db
from backend.modules.chess_intelligence.catalog_job_schemas import (
    ChessCatalogJobCreateRequest,
    ChessCatalogJobResponse,
)
from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.post("/jobs", response_model=ChessCatalogJobResponse, status_code=202)
async def enqueue_catalog_job(
    payload: ChessCatalogJobCreateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessCatalogJobResponse:
    """Queue long-running catalog work (import / enrich / sync)."""
    svc = ChessCatalogJobService(db)
    job = await svc.enqueue(
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        kind=payload.kind,
        params=payload.params,
        import_batch_id=payload.import_batch_id,
    )
    await db.commit()
    await db.refresh(job)
    svc.enqueue_celery(tenant_id=membership.tenant_id, job_id=job.id)
    return ChessCatalogJobResponse.model_validate(job)


@router.get("/jobs/{job_id}", response_model=ChessCatalogJobResponse)
async def get_catalog_job(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessCatalogJobResponse:
    job = await ChessCatalogJobService(db).get_job(
        tenant_id=membership.tenant_id, job_id=job_id
    )
    return ChessCatalogJobResponse.model_validate(job)
