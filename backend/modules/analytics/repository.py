from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.analytics.models import AnalyticsSnapshot, PostAnalytics, TemplatePerformance


class AnalyticsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_snapshot(self, snapshot: AnalyticsSnapshot) -> AnalyticsSnapshot:
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def create_post_analytics(self, analytics: PostAnalytics) -> PostAnalytics:
        self.db.add(analytics)
        await self.db.flush()
        return analytics

    async def list_snapshots(self, tenant_id: UUID, limit: int = 365) -> list[AnalyticsSnapshot]:
        result = await self.db.execute(
            select(AnalyticsSnapshot)
            .where(AnalyticsSnapshot.tenant_id == tenant_id)
            .order_by(AnalyticsSnapshot.snapshot_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_snapshot_for_post(self, published_post_id: UUID, snapshot_date: date) -> AnalyticsSnapshot | None:
        result = await self.db.execute(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.published_post_id == published_post_id,
                AnalyticsSnapshot.snapshot_date == snapshot_date,
            )
        )
        return result.scalar_one_or_none()

    async def get_template_performance(
        self, tenant_id: UUID, platform: str, tone: str, content_vertical: str
    ) -> TemplatePerformance | None:
        result = await self.db.execute(
            select(TemplatePerformance).where(
                TemplatePerformance.tenant_id == tenant_id,
                TemplatePerformance.platform == platform,
                TemplatePerformance.tone == tone,
                TemplatePerformance.content_vertical == content_vertical,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_template_performance(self, tp: TemplatePerformance) -> TemplatePerformance:
        self.db.add(tp)
        await self.db.flush()
        return tp

    async def list_template_performance(
        self, tenant_id: UUID, platform: str | None = None
    ) -> list[TemplatePerformance]:
        q = select(TemplatePerformance).where(TemplatePerformance.tenant_id == tenant_id)
        if platform:
            q = q.where(TemplatePerformance.platform == platform)
        q = q.order_by(TemplatePerformance.engagement_score.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())
