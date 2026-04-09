from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.story_intelligence.models import (
    NormalizedArticle,
    StoryCluster,
    StoryClusterArticle,
    TrendCandidate,
    TrendWorkflowState,
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

    async def get_trend_candidate_for_cluster(
        self,
        tenant_id: UUID,
        cluster_id: UUID,
    ) -> TrendCandidate | None:
        result = await self.db.execute(
            select(TrendCandidate)
            .where(
                TrendCandidate.tenant_id == tenant_id,
                TrendCandidate.story_cluster_id == cluster_id,
            )
            .order_by(TrendCandidate.date_bucket.desc(), TrendCandidate.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_trend_candidate(self, candidate: TrendCandidate) -> TrendCandidate:
        self.db.add(candidate)
        await self.db.flush()
        return candidate

    async def list_trend_candidates(
        self,
        tenant_id: UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[TrendCandidate]:
        query = (
            select(TrendCandidate)
            .where(TrendCandidate.tenant_id == tenant_id)
            .order_by(TrendCandidate.final_score.desc(), TrendCandidate.created_at.desc())
            .limit(limit)
        )
        if status:
            query = query.where(TrendCandidate.status == status)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_trend_candidate(self, tenant_id: UUID, candidate_id: UUID) -> TrendCandidate | None:
        result = await self.db.execute(
            select(TrendCandidate).where(
                TrendCandidate.tenant_id == tenant_id,
                TrendCandidate.id == candidate_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_clusters(
        self,
        *,
        tenant_id: UUID,
        worthy_only: bool = False,
        limit: int = 50,
    ) -> list[StoryCluster]:
        # Correlated subquery: latest trend score per cluster for ranking
        latest_score_subq = (
            select(TrendScore.score)
            .where(TrendScore.story_cluster_id == StoryCluster.id)
            .order_by(TrendScore.created_at.desc())
            .limit(1)
            .correlate(StoryCluster)
            .scalar_subquery()
        )
        query = (
            select(StoryCluster)
            .where(StoryCluster.tenant_id == tenant_id, StoryCluster.deleted_at.is_(None))
            .order_by(latest_score_subq.desc().nullslast(), StoryCluster.created_at.desc())
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

    async def count_recent_cluster_articles(self, cluster_id: UUID, within_hours: int = 3) -> int:
        """Count articles added to this cluster within the last `within_hours` hours."""
        since = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        result = await self.db.execute(
            select(func.count(StoryClusterArticle.story_cluster_id)).where(
                StoryClusterArticle.story_cluster_id == cluster_id,
                StoryClusterArticle.created_at >= since,
            )
        )
        return result.scalar_one() or 0

    async def count_distinct_sources_for_cluster(self, cluster_id: UUID) -> int:
        """Count unique source names across all normalized articles in this cluster."""
        result = await self.db.execute(
            select(func.count(distinct(NormalizedArticle.source_name)))
            .join(
                StoryClusterArticle,
                StoryClusterArticle.normalized_article_id == NormalizedArticle.id,
            )
            .where(StoryClusterArticle.story_cluster_id == cluster_id)
        )
        return result.scalar_one() or 0

    async def find_near_duplicate(
        self, tenant_id: UUID, embedding: list[float], within_hours: int = 6
    ) -> NormalizedArticle | None:
        """Return a recently ingested article with high cosine similarity (Python-side check)."""
        since = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        result = await self.db.execute(
            select(NormalizedArticle)
            .where(
                NormalizedArticle.tenant_id == tenant_id,
                NormalizedArticle.created_at >= since,
            )
            .order_by(NormalizedArticle.created_at.desc())
            .limit(200)
        )
        from backend.modules.story_intelligence.providers import cosine_similarity
        candidates = list(result.scalars().all())
        threshold = 0.97
        for candidate in candidates:
            candidate_embedding: list[float] = candidate.embedding or []
            if not candidate_embedding:
                continue
            if cosine_similarity(embedding, candidate_embedding) >= threshold:
                return candidate
        return None

    async def list_latest_trend_scores(self, tenant_id: UUID, limit: int = 30) -> list[TrendScore]:
        result = await self.db.execute(
            select(TrendScore)
            .join(StoryCluster, StoryCluster.id == TrendScore.story_cluster_id)
            .where(StoryCluster.tenant_id == tenant_id)
            .order_by(TrendScore.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_workflow_state(
        self,
        cluster: StoryCluster,
        workflow_state: TrendWorkflowState | str,
    ) -> StoryCluster:
        cluster.workflow_state = workflow_state.value if isinstance(workflow_state, TrendWorkflowState) else workflow_state
        await self.db.flush()
        return cluster
