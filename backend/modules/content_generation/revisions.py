from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.models import (
    ContentJob,
    ContentRevision,
    GeneratedAssetGroupStatus,
)
from backend.modules.content_generation.repository import ContentGenerationRepository


class _RevisionDeps(Protocol):
    db: AsyncSession
    repo: ContentGenerationRepository

    async def generate(
        self,
        *,
        tenant_id: UUID,
        plan_id: UUID,
        feedback: str | None = None,
        revision_of_job_id: UUID | None = None,
        social_account_ids: list[UUID] | None = None,
    ) -> ContentJob: ...


async def regenerate_with_feedback(
    svc: _RevisionDeps,
    *,
    tenant_id: UUID,
    job_id: UUID,
    feedback: str,
    requested_by_user_id: UUID | None,
    source_channel: str,
) -> ContentJob:
    original_job = await svc.repo.get_job(tenant_id, job_id)
    if not original_job:
        raise HTTPException(status_code=404, detail="Content job not found")
    latest_revision_number = 1
    await svc.repo.create_revision(
        ContentRevision(
            tenant_id=tenant_id,
            content_job_id=original_job.id,
            revision_number=latest_revision_number,
            feedback=feedback,
            source_channel=source_channel,
            requested_by_user_id=requested_by_user_id,
            status="processing",
            diff_summary="Regenerated copy using provided feedback",
            revision_payload={"feedback": feedback},
        )
    )
    return await svc.generate(
        tenant_id=tenant_id,
        plan_id=original_job.content_plan_id,
        feedback=feedback,
        revision_of_job_id=original_job.id,
        social_account_ids=[
            UUID(item)
            for item in (getattr(original_job, "target_social_account_ids", None) or [])
            if item
        ]
        or None,
    )


async def regenerate_asset_group(
    svc: _RevisionDeps,
    *,
    tenant_id: UUID,
    asset_group_id: UUID,
    instruction: str,
    requested_by_user_id: UUID | None,
    source_channel: str,
) -> ContentJob:
    asset_group = await svc.repo.get_asset_group(tenant_id, asset_group_id)
    if not asset_group:
        raise HTTPException(status_code=404, detail="Generated asset group not found")
    original_job = await svc.repo.get_job(tenant_id, asset_group.content_job_id)
    if not original_job:
        raise HTTPException(status_code=404, detail="Content job not found")

    asset_group.status = GeneratedAssetGroupStatus.REGENERATED.value
    asset_group.generation_trace = {
        **asset_group.generation_trace,
        "regeneration_requested_at": datetime.now(timezone.utc).isoformat(),
        "regeneration_instruction": instruction,
        "regeneration_source_channel": source_channel,
    }
    await svc.repo.create_revision(
        ContentRevision(
            tenant_id=tenant_id,
            content_job_id=original_job.id,
            revision_number=1,
            feedback=instruction,
            source_channel=source_channel,
            requested_by_user_id=requested_by_user_id,
            status="processing",
            diff_summary="Regenerated asset group using operator instructions",
            revision_payload={"asset_group_id": str(asset_group_id), "feedback": instruction},
        )
    )
    return await svc.generate(
        tenant_id=tenant_id,
        plan_id=original_job.content_plan_id,
        feedback=instruction,
        revision_of_job_id=original_job.id,
    )
