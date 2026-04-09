"""
OptimizationService — reads TemplatePerformance records and recommends
content parameters (tone, content_vertical, platform) for new content jobs.

Strategy:
  1. Query the top-N TemplatePerformance rows for the tenant (ordered by
     engagement_score DESC).
  2. Return a ranked list of ContentParameterRecommendation objects, each
     carrying the (platform, tone, content_vertical) triple plus the score
     and metadata that explains the recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.analytics.repository import AnalyticsRepository


@dataclass
class ContentParameterRecommendation:
    platform: str
    tone: str
    content_vertical: str
    engagement_score: float
    sample_count: int
    avg_impressions: float
    avg_likes: float
    avg_comments: float
    avg_shares: float
    avg_ctr: float
    approve_rate: float
    reject_rate: float
    # Explanation tokens for UI / audit
    reasons: list[str] = field(default_factory=list)


class OptimizationService:
    """
    Recommends content parameters based on historical TemplatePerformance data.

    Minimum sample threshold (MIN_SAMPLES) ensures we don't recommend based on
    a single data point.  Recommendations with fewer samples are still returned
    but marked as low-confidence.
    """

    MIN_SAMPLES = 3

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnalyticsRepository(db)

    async def recommend(
        self,
        tenant_id: UUID,
        platform: str | None = None,
        top_n: int = 5,
    ) -> list[ContentParameterRecommendation]:
        """
        Return the top-N content parameter combinations ranked by engagement_score.

        Parameters
        ----------
        platform:
            Optional platform filter (e.g. "x", "instagram"). When None,
            recommendations span all platforms.
        top_n:
            Maximum number of recommendations to return (default 5).
        """
        rows = await self.repo.list_template_performance(tenant_id, platform=platform)

        recommendations: list[ContentParameterRecommendation] = []
        for tp in rows[:top_n]:
            reasons: list[str] = []

            if tp.sample_count < self.MIN_SAMPLES:
                reasons.append(f"low_confidence: only {tp.sample_count} sample(s)")
            else:
                if tp.avg_likes > 500:
                    reasons.append("high_likes")
                if tp.avg_shares > 200:
                    reasons.append("high_shares")
                if tp.avg_ctr > 0.05:
                    reasons.append("high_ctr")
                if tp.approve_rate > 0.7:
                    reasons.append("high_approval_rate")
                if not reasons:
                    reasons.append("strong_overall_engagement")

            recommendations.append(
                ContentParameterRecommendation(
                    platform=tp.platform,
                    tone=tp.tone,
                    content_vertical=tp.content_vertical,
                    engagement_score=tp.engagement_score,
                    sample_count=tp.sample_count,
                    avg_impressions=tp.avg_impressions,
                    avg_likes=tp.avg_likes,
                    avg_comments=tp.avg_comments,
                    avg_shares=tp.avg_shares,
                    avg_ctr=tp.avg_ctr,
                    approve_rate=tp.approve_rate,
                    reject_rate=tp.reject_rate,
                    reasons=reasons,
                )
            )

        return recommendations

    async def best_tone_for_platform(
        self, tenant_id: UUID, platform: str
    ) -> str | None:
        """
        Return the single best tone for a given platform, or None if no data.
        """
        recs = await self.recommend(tenant_id, platform=platform, top_n=1)
        return recs[0].tone if recs else None

    async def best_vertical_for_platform(
        self, tenant_id: UUID, platform: str
    ) -> str | None:
        """
        Return the single best content_vertical for a given platform, or None.
        """
        recs = await self.recommend(tenant_id, platform=platform, top_n=1)
        return recs[0].content_vertical if recs else None
