from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_strategy.models import BrandProfile, ContentPlan


class ContentStrategyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_brand_profile(self, tenant_id: UUID) -> BrandProfile | None:
        result = await self.db.execute(
            select(BrandProfile)
            .where(BrandProfile.tenant_id == tenant_id, BrandProfile.deleted_at.is_(None))
            .order_by(BrandProfile.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_brand_profile(self, profile: BrandProfile) -> BrandProfile:
        self.db.add(profile)
        await self.db.flush()
        return profile

    async def list_content_plans(self, tenant_id: UUID, limit: int = 50) -> list[ContentPlan]:
        result = await self.db.execute(
            select(ContentPlan)
            .where(ContentPlan.tenant_id == tenant_id, ContentPlan.deleted_at.is_(None))
            .order_by(ContentPlan.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_content_plan(self, tenant_id: UUID, plan_id: UUID) -> ContentPlan | None:
        result = await self.db.execute(
            select(ContentPlan).where(
                ContentPlan.id == plan_id,
                ContentPlan.tenant_id == tenant_id,
                ContentPlan.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_plan_for_cluster(self, tenant_id: UUID, cluster_id: UUID) -> ContentPlan | None:
        result = await self.db.execute(
            select(ContentPlan)
            .where(
                ContentPlan.tenant_id == tenant_id,
                ContentPlan.story_cluster_id == cluster_id,
                ContentPlan.deleted_at.is_(None),
            )
            .order_by(ContentPlan.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_content_plan(self, plan: ContentPlan) -> ContentPlan:
        self.db.add(plan)
        await self.db.flush()
        return plan
