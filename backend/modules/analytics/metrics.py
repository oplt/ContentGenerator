from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import decrypt_secret
from backend.modules.analytics.models import AnalyticsSnapshot, TemplatePerformance
from backend.modules.analytics.providers import get_metrics_provider
from backend.modules.analytics.repository import AnalyticsRepository
from backend.modules.publishing.repository import PublishingRepository

logger = logging.getLogger(__name__)


class AnalyticsMetrics:
    """Provider metrics fetch, synthetic fallback, and template performance folding."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: AnalyticsRepository,
        publishing_repo: PublishingRepository,
    ) -> None:
        self.db = db
        self.repo = repo
        self.publishing_repo = publishing_repo

    async def fetch_real_metrics(
        self, post: Any, token_row: Any | None = None
    ) -> dict[str, object]:
        """Try real API metrics; fall back to synthetic data on failure."""
        platform = post.platform
        external_id = getattr(post, "external_post_id", None) or getattr(post, "platform_post_id", None)

        if settings.ANALYTICS_SYNTHETIC_MODE or not external_id:
            return self.synthetic_metrics(post)

        try:
            if token_row is None and post.social_account_id:
                token_row = await self.publishing_repo.get_token_for_account(post.social_account_id)

            access_token = ""
            if token_row and token_row.access_token_encrypted:
                access_token = decrypt_secret(token_row.access_token_encrypted)

            provider = get_metrics_provider(
                platform,
                access_token=access_token,
            )
            if provider is None:
                return self.synthetic_metrics(post)

            result = await provider.fetch(external_id)
            return {
                "impressions": result.impressions,
                "views": result.views,
                "likes": result.likes,
                "comments": result.comments,
                "shares": result.shares,
                "watch_time_seconds": result.watch_time_seconds,
                "ctr": result.ctr,
                "sync_source": result.sync_source,
                "raw_payload": result.raw_payload,
                "saves": result.saves,
                "avg_watch_duration": result.avg_watch_duration,
                "retention": result.retention,
                "profile_visits": result.profile_visits,
                "follows": result.follows,
            }
        except Exception as exc:
            logger.warning("metrics_fetch_failed platform=%s post_id=%s error=%s", platform, post.id, exc)
            return self.synthetic_metrics(post)

    @staticmethod
    def synthetic_metrics(post: Any) -> dict[str, object]:
        """Deterministic synthetic metrics (index-free version for single post)."""
        base = 100
        return {
            "impressions": base * 12,
            "views": base * 8,
            "likes": base * 2,
            "comments": base // 5,
            "shares": base // 6,
            "watch_time_seconds": base * 14,
            "ctr": 0.08,
            "sync_source": "synthetic",
            "raw_payload": {"mode": "synthetic"},
            "saves": base // 7,
            "avg_watch_duration": 12.0,
            "retention": {"00:03": 0.74, "00:10": 0.41},
            "profile_visits": base // 8,
            "follows": base // 20,
        }

    async def update_template_performance(
        self,
        tenant_id: UUID,
        snapshot: AnalyticsSnapshot,
        tone: str = "authoritative",
        content_vertical: str = "general",
    ) -> TemplatePerformance:
        """
        Atomically fold snapshot metrics into TemplatePerformance for
        (tenant, platform, tone, content_vertical).

        Concurrent syncs use PostgreSQL ON CONFLICT running averages.
        """
        provisional = TemplatePerformance(
            tenant_id=tenant_id,
            platform=snapshot.platform,
            tone=tone,
            content_vertical=content_vertical,
            sample_count=1,
            avg_impressions=float(snapshot.impressions),
            avg_likes=float(snapshot.likes),
            avg_comments=float(snapshot.comments),
            avg_shares=float(snapshot.shares),
            avg_ctr=float(snapshot.ctr or 0.0),
        )
        engagement = self.compute_engagement_score(provisional)
        tp = await self.repo.apply_template_performance_sample(
            tenant_id=tenant_id,
            platform=snapshot.platform,
            tone=tone,
            content_vertical=content_vertical,
            impressions=snapshot.impressions,
            likes=snapshot.likes,
            comments=snapshot.comments,
            shares=snapshot.shares,
            ctr=float(snapshot.ctr or 0.0),
            engagement_score=engagement,
            computed_at=datetime.now(timezone.utc),
        )
        # Recompute score from post-upsert averages (excluded score is provisional).
        tp.engagement_score = self.compute_engagement_score(tp)
        await self.db.flush()
        return tp

    @staticmethod
    def compute_engagement_score(tp: TemplatePerformance) -> float:
        """
        Composite engagement score (0–1).
        Weights: likes 40%, shares 30%, comments 20%, ctr 10%.
        Normalised by typical maximums; clamped to [0, 1].
        """
        if tp.sample_count == 0:
            return 0.0

        MAX_LIKES = 10_000
        MAX_SHARES = 5_000
        MAX_COMMENTS = 2_000

        score = (
            0.40 * min(tp.avg_likes / MAX_LIKES, 1.0)
            + 0.30 * min(tp.avg_shares / MAX_SHARES, 1.0)
            + 0.20 * min(tp.avg_comments / MAX_COMMENTS, 1.0)
            + 0.10 * min(tp.avg_ctr, 1.0)
        )
        return round(min(max(score, 0.0), 1.0), 6)

