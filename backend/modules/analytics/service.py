from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import decrypt_secret
from backend.modules.analytics.models import AnalyticsSnapshot, PostAnalytics, TemplatePerformance
from backend.modules.analytics.providers import get_metrics_provider
from backend.modules.analytics.repository import AnalyticsRepository
from backend.modules.analytics.metrics import AnalyticsMetrics
from backend.modules.analytics.overview_builder import aggregate_snapshot_charts, build_learning_log
from backend.modules.analytics.schemas import AnalyticsOverviewResponse, ChartPoint, LearningLogEntry
from backend.modules.publishing.account_ops import (
    account_label_from_snapshot,
)
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
        self.metrics = AnalyticsMetrics(db, repo=self.repo, publishing_repo=self.publishing_repo)

    async def sync_snapshots(self, tenant_id: UUID) -> list[AnalyticsSnapshot]:
        today = date.today()
        contexts = await self.repo.list_post_sync_contexts(tenant_id)
        if not contexts:
            return []

        post_ids = [ctx.post.id for ctx in contexts]
        existing_by_post = await self.repo.get_snapshots_for_posts(post_ids, today)

        account_ids = [
            ctx.post.social_account_id
            for ctx in contexts
            if getattr(ctx.post, "social_account_id", None) is not None
        ]
        tokens_by_account = await self.publishing_repo.get_tokens_for_accounts(
            list({account_id for account_id in account_ids if account_id is not None})
        )

        snapshots: list[AnalyticsSnapshot] = []
        # Bounded concurrent provider fetches; preserve context order; keep partial successes.
        from backend.core.config import settings as app_settings
        from backend.core.http import map_concurrent

        async def _metrics_for(ctx: Any) -> dict[str, object]:
            post = ctx.post
            return await self.metrics.fetch_real_metrics(
                post,
                token_row=tokens_by_account.get(post.social_account_id)
                if post.social_account_id
                else None,
            )

        metrics_outcomes = await map_concurrent(
            contexts,
            _metrics_for,
            limit=app_settings.HTTP_PROVIDER_ANALYTICS_CONCURRENCY,
            return_exceptions=True,
        )

        for ctx, metrics_outcome in zip(contexts, metrics_outcomes, strict=True):
            post = ctx.post
            if isinstance(metrics_outcome, BaseException):
                logger.warning(
                    "metrics_fetch_failed platform=%s post_id=%s error=%s",
                    post.platform,
                    post.id,
                    metrics_outcome,
                )
                metrics = self._synthetic_metrics(post)
            else:
                metrics = metrics_outcome
            impressions = int(cast(int, metrics["impressions"]))
            views = int(cast(int, metrics["views"]))
            likes = int(cast(int, metrics["likes"]))
            comments = int(cast(int, metrics["comments"]))
            shares = int(cast(int, metrics["shares"]))
            watch_time_seconds = int(cast(int, metrics["watch_time_seconds"]))
            ctr = float(cast(float, metrics["ctr"]))
            sync_source = str(cast(str, metrics["sync_source"]))
            raw_payload = cast(dict[str, str], metrics.get("raw_payload") or {})
            saves = int(cast(int, metrics.get("saves", 0)))
            avg_watch_duration = cast(float | None, metrics.get("avg_watch_duration"))
            retention = cast(dict[str, str], metrics.get("retention") or {})
            profile_visits = int(cast(int, metrics.get("profile_visits", 0)))
            follows = int(cast(int, metrics.get("follows", 0)))

            account_label = account_label_from_snapshot(
                getattr(post, "account_display_snapshot", None) or {},
                platform=str(post.platform),
            )
            snapshot, was_inserted = await self.repo.upsert_snapshot(
                tenant_id=tenant_id,
                published_post_id=post.id,
                platform=post.platform,
                snapshot_date=today,
                topic=post.raw_payload.get("topic") if post.raw_payload else None,
                content_format=post.post_type,
                impressions=impressions,
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                watch_time_seconds=watch_time_seconds,
                ctr=ctr,
                sync_source=sync_source,
                raw_payload=raw_payload,
                social_account_id=post.social_account_id,
                account_label=account_label,
            )
            # Prefer bulk-loaded existence when xmax trick unavailable (non-PG)
            if post.id in existing_by_post:
                was_inserted = False
            snapshots.append(snapshot)

            self.db.add(
                PostAnalytics(
                    tenant_id=tenant_id,
                    publish_job_id=ctx.publish_job_id,
                    published_post_id=post.id,
                    platform=post.platform,
                    fetched_at=datetime.now(timezone.utc),
                    impressions=impressions,
                    views=views,
                    likes=likes,
                    comments=comments,
                    shares=shares,
                    saves=saves,
                    watch_time=watch_time_seconds,
                    avg_watch_duration=avg_watch_duration,
                    retention=retention,
                    profile_visits=profile_visits,
                    follows=follows,
                    ctr=ctr,
                    raw_metrics=raw_payload,
                )
            )

            # Only fold new daily snapshots into aggregates — re-sync must not double-count.
            if was_inserted:
                try:
                    await self.update_template_performance(
                        tenant_id,
                        snapshot,
                        tone=ctx.tone,
                        content_vertical=ctx.content_vertical,
                    )
                except Exception:
                    pass  # Performance tracking must never block metrics sync

        await self.db.flush()
        return snapshots

    async def _resolve_post_context(self, post: Any) -> tuple[str, str]:
        """
        Look up (tone, content_vertical) for a published post by tracing
        PublishedPost → PublishingJob → ContentJob → ContentPlan → StoryCluster.
        Returns defaults ("authoritative", "general") if the chain cannot be resolved.

        Prefer list_post_sync_contexts() for batch sync paths.
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

    async def _fetch_real_metrics(
        self, post: Any, token_row: Any | None = None
    ) -> dict[str, object]:
        return await self.metrics.fetch_real_metrics(post, token_row=token_row)

    @staticmethod
    def _synthetic_metrics(post: Any) -> dict[str, object]:
        return AnalyticsMetrics.synthetic_metrics(post)

    async def update_template_performance(
        self,
        tenant_id: UUID,
        snapshot: AnalyticsSnapshot,
        tone: str = "authoritative",
        content_vertical: str = "general",
    ) -> TemplatePerformance:
        return await self.metrics.update_template_performance(
            tenant_id, snapshot, tone=tone, content_vertical=content_vertical
        )

    @staticmethod
    def _compute_engagement_score(tp: TemplatePerformance) -> float:
        return AnalyticsMetrics.compute_engagement_score(tp)

    async def overview(
        self,
        tenant_id: UUID,
        *,
        social_account_id: UUID | None = None,
    ) -> AnalyticsOverviewResponse:
        snapshots = await self.repo.list_snapshots(
            tenant_id, social_account_id=social_account_id
        )
        posts = await self.publishing_repo.list_published_posts(tenant_id)
        if social_account_id is not None:
            posts = [post for post in posts if post.social_account_id == social_account_id]
        sources = await self.source_repo.list_sources(tenant_id)
        clusters = await self.story_repo.list_clusters(tenant_id=tenant_id)

        summary: list[dict[str, str | float | int]] = [
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

        charts = aggregate_snapshot_charts(snapshots)
        posts_by_date = charts["posts_by_date"]
        by_platform = charts["by_platform"]
        by_account = charts["by_account"]
        by_format = charts["by_format"]
        by_topic = charts["by_topic"]
        hook_performance_raw = charts["hook_performance_raw"]
        post_time_raw = charts["post_time_raw"]
        brand_performance_raw = charts["brand_performance_raw"]
        topic_follow_raw = charts["topic_follow_raw"]
        platform_comparison_raw = charts["platform_comparison_raw"]

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
        learning_log = await build_learning_log(
            self.db,
            tenant_id=tenant_id,
            platform_views=by_platform,
            topic_views=by_topic,
            post_time=post_time_raw,
        )

        return AnalyticsOverviewResponse(
            summary=summary,
            posts_over_time=[ChartPoint(label=label, value=value) for label, value in posts_by_date.items()],
            engagement_by_platform=[ChartPoint(label=label, value=value) for label, value in by_platform.items()],
            engagement_by_account=[ChartPoint(label=label, value=value) for label, value in by_account.items()],
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
            filtered_social_account_id=str(social_account_id) if social_account_id else None,
        )
