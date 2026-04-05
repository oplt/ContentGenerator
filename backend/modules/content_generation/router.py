from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.content_generation.schemas import ContentJobResponse, GenerateContentRequest, RegenerateContentRequest
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.get("/jobs", response_model=list[ContentJobResponse])
async def list_content_jobs(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ContentJobResponse]:
    service = ContentGenerationService(db)
    jobs = await service.list_jobs(membership.tenant_id)
    return [await service.get_job_detail(membership.tenant_id, job.id) for job in jobs]


@router.get("/jobs/{job_id}", response_model=ContentJobResponse)
async def get_content_job(
    job_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> ContentJobResponse:
    service = ContentGenerationService(db)
    return await service.get_job_detail(membership.tenant_id, job_id)


@router.post("/generate", response_model=ContentJobResponse, status_code=201)
async def generate_content(
    payload: GenerateContentRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ContentJobResponse:
    service = ContentGenerationService(db)
    job = await service.generate(tenant_id=membership.tenant_id, plan_id=payload.content_plan_id)
    await db.commit()
    return await service.get_job_detail(membership.tenant_id, job.id)


@router.post("/jobs/{job_id}/regenerate", response_model=ContentJobResponse)
async def regenerate_content(
    job_id: UUID,
    payload: RegenerateContentRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> ContentJobResponse:
    service = ContentGenerationService(db)
    job = await service.regenerate_with_feedback(
        tenant_id=membership.tenant_id,
        job_id=job_id,
        feedback=payload.feedback,
        requested_by_user_id=membership.user_id,
        source_channel="dashboard",
    )
    await db.commit()
    return await service.get_job_detail(membership.tenant_id, job.id)
