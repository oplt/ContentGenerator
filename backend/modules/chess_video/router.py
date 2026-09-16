"""Chess video HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import require_permission
from backend.api.deps.db import get_db
from backend.modules.chess_intelligence.provenance_schemas import ChessVideoProvenanceResponse
from backend.modules.chess_intelligence.provenance_service import ChessProvenanceService
from backend.modules.chess_video.models import ChessVideoJobStatus
from backend.modules.chess_video.schemas import (
    ChessVideoCreateRequest,
    ChessVideoJobResponse,
    ChessVideoValidateRequest,
    ChessVideoValidateResponse,
)
from backend.modules.chess_video.service import ChessVideoService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.post("/validate", response_model=ChessVideoValidateResponse)
async def validate_chess_video(
    payload: ChessVideoValidateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoValidateResponse:
    _ = membership
    return await ChessVideoService(db).validate(payload)


@router.post("", response_model=ChessVideoJobResponse, status_code=201)
async def create_chess_video(
    payload: ChessVideoCreateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoJobResponse:
    service = ChessVideoService(db)
    job = await service.create(
        tenant_id=membership.tenant_id,
        user_id=membership.user_id,
        payload=payload,
    )
    await db.commit()
    await db.refresh(job)
    if job.status == ChessVideoJobStatus.QUEUED.value:
        service.enqueue_job(tenant_id=membership.tenant_id, job_id=job.id)
    return ChessVideoJobResponse.model_validate(job)


@router.get("", response_model=list[ChessVideoJobResponse])
async def list_chess_videos(
    limit: int = Query(default=50, ge=1, le=100),
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> list[ChessVideoJobResponse]:
    jobs = await ChessVideoService(db).list(tenant_id=membership.tenant_id, limit=limit)
    return [ChessVideoJobResponse.model_validate(job) for job in jobs]


@router.get("/{job_id}/provenance", response_model=ChessVideoProvenanceResponse)
async def get_chess_video_provenance(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoProvenanceResponse:
    """Trace: video → catalog game (if linked) → provider sources → PGN."""
    return await ChessProvenanceService(db).for_video(
        tenant_id=membership.tenant_id, job_id=job_id
    )


@router.get("/{job_id}", response_model=ChessVideoJobResponse)
async def get_chess_video(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoJobResponse:
    job = await ChessVideoService(db).get(tenant_id=membership.tenant_id, job_id=job_id)
    return ChessVideoJobResponse.model_validate(job)


@router.post("/{job_id}/retry", response_model=ChessVideoJobResponse)
async def retry_chess_video(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ChessVideoJobResponse:
    service = ChessVideoService(db)
    job = await service.retry(tenant_id=membership.tenant_id, job_id=job_id)
    await db.commit()
    await db.refresh(job)
    service.enqueue_job(tenant_id=membership.tenant_id, job_id=job.id)
    return ChessVideoJobResponse.model_validate(job)


@router.delete("/{job_id}", status_code=204)
async def delete_chess_video(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = ChessVideoService(db)
    cleanup = await service.delete(
        tenant_id=membership.tenant_id,
        job_id=job_id,
    )
    await db.commit()
    await ChessVideoService.cleanup_storage(cleanup=cleanup)
    return Response(status_code=204)
