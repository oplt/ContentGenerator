from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief


class EditorialBriefRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, brief: EditorialBrief) -> EditorialBrief:
        self.db.add(brief)
        await self.db.flush()
        return brief

    async def get(self, tenant_id: UUID, brief_id: UUID) -> EditorialBrief | None:
        result = await self.db.execute(
            select(EditorialBrief).where(
                EditorialBrief.id == brief_id,
                EditorialBrief.tenant_id == tenant_id,
                EditorialBrief.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_cluster(self, tenant_id: UUID, story_cluster_id: UUID) -> EditorialBrief | None:
        result = await self.db.execute(
            select(EditorialBrief).where(
                EditorialBrief.story_cluster_id == story_cluster_id,
                EditorialBrief.tenant_id == tenant_id,
                EditorialBrief.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EditorialBrief]:
        q = select(EditorialBrief).where(
            EditorialBrief.tenant_id == tenant_id,
            EditorialBrief.deleted_at.is_(None),
        )
        if status:
            q = q.where(EditorialBrief.status == status)
        q = q.order_by(EditorialBrief.created_at.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_by_telegram_short_id(self, short_id: str) -> EditorialBrief | None:
        result = await self.db.execute(
            select(EditorialBrief).where(
                EditorialBrief.telegram_short_id == short_id,
                EditorialBrief.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()
