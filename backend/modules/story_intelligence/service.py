"""Story intelligence service facade — clustering, scoring, and trend workflow."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.story_intelligence.cluster_pipeline import ClusterPipelineMixin
from backend.modules.story_intelligence.providers import (
    get_embeddings_provider,
    get_llm_provider,
)
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.story_intelligence.scoring import ClusterScorer, STOPWORDS as SCORER_STOPWORDS
from backend.modules.story_intelligence.trend_candidates import TrendCandidateMixin

STOPWORDS = SCORER_STOPWORDS


class StoryIntelligenceService(ClusterPipelineMixin, TrendCandidateMixin):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryIntelligenceRepository(db)
        self.strategy_repo = ContentStrategyRepository(db)
        self.audit = AuditService(db)
        self.llm = get_llm_provider()
        self.embeddings = get_embeddings_provider()
        self.fact_review = FactRiskReviewService()
        self.scorer = ClusterScorer(
            db, repo=self.repo, fact_review_service=self.fact_review, llm=self.llm
        )

    def _fact_review_service(self) -> FactRiskReviewService:
        if not hasattr(self, "fact_review") or self.fact_review is None:
            self.fact_review = FactRiskReviewService()
        return self.fact_review
