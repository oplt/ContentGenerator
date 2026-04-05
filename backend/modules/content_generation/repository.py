from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.models import ContentJob, ContentRevision, GeneratedAsset


class ContentGenerationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_job(self, job: ContentJob) -> ContentJob:
        self.db.add(job)
        await self.db.flush()
        return job

    async def create_revision(self, revision: ContentRevision) -> ContentRevision:
        self.db.add(revision)
        await self.db.flush()
        return revision

    async def list_jobs(self, tenant_id: UUID, limit: int = 50) -> list[ContentJob]:
        result = await self.db.execute(
            select(ContentJob)
            .where(ContentJob.tenant_id == tenant_id)
            .order_by(ContentJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_job(self, tenant_id: UUID, job_id: UUID) -> ContentJob | None:
        result = await self.db.execute(
            select(ContentJob).where(ContentJob.id == job_id, ContentJob.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_assets(self, job_id: UUID) -> list[GeneratedAsset]:
        result = await self.db.execute(
            select(GeneratedAsset)
            .where(GeneratedAsset.content_job_id == job_id, GeneratedAsset.deleted_at.is_(None))
            .order_by(GeneratedAsset.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_latest_job_for_plan(self, plan_id: UUID) -> ContentJob | None:
        result = await self.db.execute(
            select(ContentJob)
            .where(ContentJob.content_plan_id == plan_id)
            .order_by(ContentJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
