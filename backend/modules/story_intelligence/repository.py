from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.story_intelligence.models import (
    NormalizedArticle,
    StoryCluster,
    StoryClusterArticle,
    TrendScore,
)


class StoryIntelligenceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_normalized_by_raw_article(self, raw_article_id: UUID) -> NormalizedArticle | None:
        result = await self.db.execute(
            select(NormalizedArticle).where(NormalizedArticle.raw_article_id == raw_article_id)
        )
        return result.scalar_one_or_none()

    async def create_normalized_article(self, article: NormalizedArticle) -> NormalizedArticle:
        self.db.add(article)
        await self.db.flush()
        return article

    async def list_recent_clusters(self, tenant_id: UUID, within_hours: int = 72) -> list[StoryCluster]:
        since = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        result = await self.db.execute(
            select(StoryCluster).where(
                StoryCluster.tenant_id == tenant_id,
                StoryCluster.deleted_at.is_(None),
                StoryCluster.created_at >= since,
            )
        )
        return list(result.scalars().all())

    async def create_cluster(self, cluster: StoryCluster) -> StoryCluster:
        self.db.add(cluster)
        await self.db.flush()
        return cluster

    async def add_cluster_article(self, item: StoryClusterArticle) -> StoryClusterArticle:
        self.db.add(item)
        await self.db.flush()
        return item

    async def get_cluster_articles(self, cluster_id: UUID) -> list[StoryClusterArticle]:
        result = await self.db.execute(
            select(StoryClusterArticle).where(StoryClusterArticle.story_cluster_id == cluster_id)
        )
        return list(result.scalars().all())

    async def get_latest_trend_score(self, cluster_id: UUID) -> TrendScore | None:
        result = await self.db.execute(
            select(TrendScore)
            .where(TrendScore.story_cluster_id == cluster_id)
            .order_by(TrendScore.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_trend_score(self, trend_score: TrendScore) -> TrendScore:
        self.db.add(trend_score)
        await self.db.flush()
        return trend_score

    async def list_clusters(
        self,
        *,
        tenant_id: UUID,
        worthy_only: bool = False,
        limit: int = 50,
    ) -> list[StoryCluster]:
        query = (
            select(StoryCluster)
            .where(StoryCluster.tenant_id == tenant_id, StoryCluster.deleted_at.is_(None))
            .order_by(StoryCluster.created_at.desc())
            .limit(limit)
        )
        if worthy_only:
            query = query.where(StoryCluster.worthy_for_content.is_(True))
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_cluster(self, tenant_id: UUID, cluster_id: UUID) -> StoryCluster | None:
        result = await self.db.execute(
            select(StoryCluster).where(
                StoryCluster.id == cluster_id,
                StoryCluster.tenant_id == tenant_id,
                StoryCluster.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_cluster_articles(self, cluster_id: UUID) -> list[StoryClusterArticle]:
        result = await self.db.execute(
            select(StoryClusterArticle).where(StoryClusterArticle.story_cluster_id == cluster_id)
        )
        return list(result.scalars().all())

    async def list_normalized_for_cluster(self, cluster_id: UUID) -> list[NormalizedArticle]:
        result = await self.db.execute(
            select(NormalizedArticle)
            .join(
                StoryClusterArticle,
                StoryClusterArticle.normalized_article_id == NormalizedArticle.id,
            )
            .where(StoryClusterArticle.story_cluster_id == cluster_id)
            .order_by(NormalizedArticle.published_at.desc().nullslast(), NormalizedArticle.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_latest_trend_scores(self, tenant_id: UUID, limit: int = 30) -> list[TrendScore]:
        result = await self.db.execute(
            select(TrendScore)
            .join(StoryCluster, StoryCluster.id == TrendScore.story_cluster_id)
            .where(StoryCluster.tenant_id == tenant_id)
            .order_by(TrendScore.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
