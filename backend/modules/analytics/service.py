from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import decrypt_secret
from backend.modules.analytics.models import AnalyticsSnapshot, PostAnalytics, TemplatePerformance
from backend.modules.analytics.providers import get_metrics_provider
from backend.modules.analytics.repository import AnalyticsRepository
from backend.modules.analytics.schemas import AnalyticsOverviewResponse, ChartPoint, LearningLogEntry
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository

logger = logging.getLogger(__name__)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AnalyticsRepository(db)
        self.publishing_repo = PublishingRepository(db)
        self.source_repo = SourceRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)

    async def sync_snapshots(self, tenant_id: UUID) -> list[AnalyticsSnapshot]:
        today = date.today()
        posts = await self.publishing_repo.list_published_posts(tenant_id)
        snapshots: list[AnalyticsSnapshot] = []

        for index, post in enumerate(posts):
            existing = await self.repo.get_snapshot_for_post(post.id, today)
            publish_job = await self.publishing_repo.get_publishing_job(tenant_id, post.publishing_job_id)
            if not publish_job:
                continue

            # Try to fetch real metrics from the platform API
            metrics = await self._fetch_real_metrics(post)

            if existing:
                existing.impressions = metrics["impressions"]
                existing.views = metrics["views"]
                existing.likes = metrics["likes"]
                existing.comments = metrics["comments"]
                existing.shares = metrics["shares"]
                existing.watch_time_seconds = metrics["watch_time_seconds"]
                existing.ctr = metrics["ctr"]
                existing.sync_source = metrics["sync_source"]
                if metrics.get("raw_payload"):
                    existing.raw_payload = metrics["raw_payload"]
                snapshot = existing
            else:
                snapshot = await self.repo.create_snapshot(
                    AnalyticsSnapshot(
                        tenant_id=tenant_id,
                        published_post_id=post.id,
                        platform=post.platform,
                        snapshot_date=today,
                        topic=post.raw_payload.get("topic"),
                        content_format=post.post_type,
                        impressions=metrics["impressions"],
                        views=metrics["views"],
                        likes=metrics["likes"],
                        comments=metrics["comments"],
                        shares=metrics["shares"],
                        watch_time_seconds=metrics["watch_time_seconds"],
                        ctr=metrics["ctr"],
                        sync_source=metrics["sync_source"],
                        raw_payload=metrics.get("raw_payload") or {},
                    )
                )
            snapshots.append(snapshot)
            await self.repo.create_post_analytics(
                PostAnalytics(
                    tenant_id=tenant_id,
                    publish_job_id=publish_job.id,
                    published_post_id=post.id,
                    platform=post.platform,
                    fetched_at=datetime.now(timezone.utc),
                    impressions=metrics["impressions"],
                    views=metrics["views"],
                    likes=metrics["likes"],
                    comments=metrics["comments"],
                    shares=metrics["shares"],
                    saves=metrics.get("saves", 0),
                    watch_time=metrics["watch_time_seconds"],
                    avg_watch_duration=metrics.get("avg_watch_duration"),
                    retention=metrics.get("retention") or {},
                    profile_visits=metrics.get("profile_visits", 0),
                    follows=metrics.get("follows", 0),
                    ctr=metrics["ctr"],
                    raw_metrics=metrics.get("raw_payload") or {},
                )
            )

            # Feed this snapshot into the TemplatePerformance aggregate so that
            # OptimizationService can recommend better content parameters next time.
            tone, content_vertical = await self._resolve_post_context(post)
            try:
                await self.update_template_performance(tenant_id, snapshot, tone=tone, content_vertical=content_vertical)
            except Exception:
                pass  # Performance tracking must never block metrics sync

        await self.db.flush()
        return snapshots

    async def _resolve_post_context(self, post) -> tuple[str, str]:
        """
        Look up (tone, content_vertical) for a published post by tracing
        PublishedPost → PublishingJob → ContentJob → ContentPlan → StoryCluster.
        Returns defaults ("authoritative", "general") if the chain cannot be resolved.
        """
        try:
            from backend.modules.content_generation.repository import ContentGenerationRepository
            from backend.modules.content_strategy.repository import ContentStrategyRepository

            pub_job = await self.publishing_repo.get_publishing_job(
                post.tenant_id, post.publishing_job_id
            )
            if not pub_job:
                return "authoritative", "general"

            content_repo = ContentGenerationRepository(self.db)
            content_job = await content_repo.get_job(post.tenant_id, pub_job.content_job_id)
            if not content_job:
                return "authoritative", "general"

            plan_repo = ContentStrategyRepository(self.db)
            plan = await plan_repo.get_content_plan(post.tenant_id, content_job.content_plan_id)
            if not plan:
                return "authoritative", "general"

            cluster = await self.story_repo.get_cluster(post.tenant_id, plan.story_cluster_id)
            vertical = (getattr(cluster, "content_vertical", None) or "general") if cluster else "general"
            return plan.tone or "authoritative", vertical
        except Exception:
            return "authoritative", "general"

    async def _fetch_real_metrics(self, post) -> dict:
        """Try real API metrics; fall back to synthetic data on failure."""
        platform = post.platform
        external_id = getattr(post, "external_post_id", None) or getattr(post, "platform_post_id", None)

        if settings.ANALYTICS_SYNTHETIC_MODE or not external_id:
            return self._synthetic_metrics(post)

        try:
            # Retrieve the social account token for this post's account
            token_row = None
            if post.social_account_id:
                token_row = await self.publishing_repo.get_token_for_account(post.social_account_id)

            access_token = ""
            if token_row and token_row.access_token_encrypted:
                access_token = decrypt_secret(token_row.access_token_encrypted)

            provider = get_metrics_provider(
                platform,
                access_token=access_token,
            )
            if provider is None:
                return self._synthetic_metrics(post)

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
            return self._synthetic_metrics(post)

    @staticmethod
    def _synthetic_metrics(post) -> dict:
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
        Incrementally update the TemplatePerformance aggregate for
        (tenant, platform, tone, content_vertical) using new snapshot data.
        Uses a running weighted average to avoid re-scanning all snapshots.
        """
        tp = await self.repo.get_template_performance(
            tenant_id, snapshot.platform, tone, content_vertical
        )
        if tp is None:
            tp = TemplatePerformance(
                tenant_id=tenant_id,
                platform=snapshot.platform,
                tone=tone,
                content_vertical=content_vertical,
                sample_count=0,
                avg_impressions=0.0,
                avg_likes=0.0,
                avg_comments=0.0,
                avg_shares=0.0,
                avg_ctr=0.0,
                approve_rate=0.0,
                revise_rate=0.0,
                reject_rate=0.0,
                engagement_score=0.0,
            )

        n = tp.sample_count
        # Incremental mean: new_avg = (old_avg * n + new_value) / (n + 1)
        tp.avg_impressions = (tp.avg_impressions * n + snapshot.impressions) / (n + 1)
        tp.avg_likes = (tp.avg_likes * n + snapshot.likes) / (n + 1)
        tp.avg_comments = (tp.avg_comments * n + snapshot.comments) / (n + 1)
        tp.avg_shares = (tp.avg_shares * n + snapshot.shares) / (n + 1)
        ctr = snapshot.ctr or 0.0
        tp.avg_ctr = (tp.avg_ctr * n + ctr) / (n + 1)
        tp.sample_count = n + 1
        tp.engagement_score = self._compute_engagement_score(tp)
        tp.last_computed_at = datetime.now(timezone.utc)

        return await self.repo.upsert_template_performance(tp)

    @staticmethod
    def _compute_engagement_score(tp: TemplatePerformance) -> float:
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

    async def overview(self, tenant_id: UUID) -> AnalyticsOverviewResponse:
        snapshots = await self.repo.list_snapshots(tenant_id)
        posts = await self.publishing_repo.list_published_posts(tenant_id)
        sources = await self.source_repo.list_sources(tenant_id)
        clusters = await self.story_repo.list_clusters(tenant_id=tenant_id)

        summary = [
            {
                "key": "posts",
                "label": "Published posts",
                "value": len(posts),
            },
            {
                "key": "views",
                "label": "Views",
                "value": sum(snapshot.views for snapshot in snapshots),
            },
            {
                "key": "engagement",
                "label": "Engagement",
                "value": sum(snapshot.likes + snapshot.comments + snapshot.shares for snapshot in snapshots),
            },
        ]

        posts_by_date: dict[str, float] = defaultdict(float)
        by_platform: dict[str, float] = defaultdict(float)
        by_format: dict[str, float] = defaultdict(float)
        by_topic: dict[str, float] = defaultdict(float)
        hook_performance_raw: dict[str, float] = defaultdict(float)
        post_time_raw: dict[str, float] = defaultdict(float)
        brand_performance_raw: dict[str, float] = defaultdict(float)
        topic_follow_raw: dict[str, float] = defaultdict(float)
        platform_comparison_raw: dict[str, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
        for snapshot in snapshots:
            posts_by_date[str(snapshot.snapshot_date)] += snapshot.views
            by_platform[snapshot.platform] += snapshot.views
            by_format[snapshot.content_format] += snapshot.views
            raw_payload = snapshot.raw_payload or {}
            hook_label = str(raw_payload.get("hook") or raw_payload.get("hook_label") or "default")
            hook_performance_raw[hook_label] += snapshot.views
            post_hour = str(raw_payload.get("publish_hour") or "unknown")
            post_time_raw[post_hour] += snapshot.views
            brand_label = str(raw_payload.get("brand") or raw_payload.get("brand_profile") or "default")
            brand_performance_raw[brand_label] += snapshot.views
            current_views, current_engagement = platform_comparison_raw[snapshot.platform]
            platform_comparison_raw[snapshot.platform] = (
                current_views + snapshot.views,
                current_engagement + snapshot.likes + snapshot.comments + snapshot.shares,
            )
            if snapshot.topic:
                by_topic[snapshot.topic] += snapshot.views
                topic_follow_raw[snapshot.topic] += float(raw_payload.get("follows", 0))

        publishing_funnel = [
            ChartPoint(label="Generated", value=len(clusters)),
            ChartPoint(label="Approved", value=len(posts)),
            ChartPoint(label="Published", value=len(posts)),
            ChartPoint(label="Tracked", value=len(snapshots)),
        ]
        source_reliability = [
            ChartPoint(
                label=source.name,
                value=source.success_count,
                secondary=float(source.failure_count),
            )
            for source in sources[:8]
        ]
        platform_comparison = [
            ChartPoint(label=label, value=views, secondary=engagement)
            for label, (views, engagement) in platform_comparison_raw.items()
        ]
        learning_log = await self._build_learning_log(
            tenant_id=tenant_id,
            platform_views=by_platform,
            topic_views=by_topic,
            post_time=post_time_raw,
        )

        return AnalyticsOverviewResponse(
            summary=summary,
            posts_over_time=[ChartPoint(label=label, value=value) for label, value in posts_by_date.items()],
            engagement_by_platform=[ChartPoint(label=label, value=value) for label, value in by_platform.items()],
            format_performance=[ChartPoint(label=label, value=value) for label, value in by_format.items()],
            topic_performance=[ChartPoint(label=label, value=value) for label, value in by_topic.items()],
            publishing_funnel=publishing_funnel,
            source_reliability=source_reliability,
            hook_performance=[ChartPoint(label=label, value=value) for label, value in hook_performance_raw.items()],
            post_time_performance=[ChartPoint(label=label, value=value) for label, value in post_time_raw.items()],
            brand_performance=[ChartPoint(label=label, value=value) for label, value in brand_performance_raw.items()],
            topic_to_follower_conversion=[ChartPoint(label=label, value=value) for label, value in topic_follow_raw.items()],
            platform_comparison=platform_comparison,
            learning_log=learning_log,
        )

    async def _build_learning_log(
        self,
        *,
        tenant_id: UUID,
        platform_views: dict[str, float],
        topic_views: dict[str, float],
        post_time: dict[str, float],
    ) -> list[LearningLogEntry]:
        learning_log: list[LearningLogEntry] = []
        total_platform_views = sum(platform_views.values()) or 1.0
        for platform, views in sorted(platform_views.items(), key=lambda item: item[1], reverse=True)[:3]:
            learning_log.append(
                LearningLogEntry(
                    category="scoring_weight",
                    message=f"Platform weight shifted toward {platform}",
                    weight=round(views / total_platform_views, 4),
                    recommendation=f"Prefer prompts tailored for {platform}",
                )
            )
        for topic, _views in sorted(topic_views.items(), key=lambda item: item[1], reverse=True)[:2]:
            learning_log.append(
                LearningLogEntry(
                    category="prompt_recommendation",
                    message=f"Topic '{topic}' is outperforming current baseline",
                    recommendation=f"Increase hook density and CTA specificity for {topic}",
                )
            )
        for hour, _views in sorted(post_time.items(), key=lambda item: item[1], reverse=True)[:1]:
            learning_log.append(
                LearningLogEntry(
                    category="publish_timing",
                    message=f"Best publish hour currently {hour}",
                    recommendation="Bias schedules toward the strongest hour bucket",
                )
            )
        try:
            from backend.modules.analytics.optimization import OptimizationService

            recommendations = await OptimizationService(self.db).recommend(tenant_id, top_n=2)
            for rec in recommendations:
                learning_log.append(
                    LearningLogEntry(
                        category="prompt_recommendation",
                        message=f"Top template for {rec.platform}: tone={rec.tone}, vertical={rec.content_vertical}",
                        weight=rec.engagement_score,
                        recommendation=", ".join(rec.reasons),
                    )
                )
        except Exception:
            pass
        return learning_log
