"""Persistence for chess video jobs."""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_video.models import ChessVideoJob


class ChessVideoRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, job: ChessVideoJob) -> ChessVideoJob:
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_for_tenant(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessVideoJob | None:
        result = await self.db.execute(
            select(ChessVideoJob).where(
                ChessVideoJob.id == job_id,
                ChessVideoJob.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(
        self, *, tenant_id: uuid.UUID, limit: int = 50
    ) -> Sequence[ChessVideoJob]:
        result = await self.db.execute(
            select(ChessVideoJob)
            .where(ChessVideoJob.tenant_id == tenant_id)
            .order_by(ChessVideoJob.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def find_reusable_completed(
        self,
        *,
        tenant_id: uuid.UUID,
        render_fingerprint: str,
    ) -> ChessVideoJob | None:
        """Return a completed job with the same fingerprint that still has a video URL."""
        result = await self.db.execute(
            select(ChessVideoJob)
            .where(
                ChessVideoJob.tenant_id == tenant_id,
                ChessVideoJob.render_fingerprint == render_fingerprint,
                ChessVideoJob.status == "completed",
                ChessVideoJob.video_public_url.is_not(None),
            )
            .order_by(ChessVideoJob.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete(self, job: ChessVideoJob) -> None:
        await self.db.delete(job)
        await self.db.flush()
