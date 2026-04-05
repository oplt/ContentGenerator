from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.analytics.models import AnalyticsSnapshot
from backend.modules.analytics.repository import AnalyticsRepository
from backend.modules.analytics.schemas import AnalyticsOverviewResponse, ChartPoint
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


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
            base = (index + 1) * 100
            if existing:
                existing.impressions = base * 12
                existing.views = base * 8
                existing.likes = base * 2
                existing.comments = base // 5
                existing.shares = base // 6
                existing.watch_time_seconds = base * 14
                existing.ctr = 0.08
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
                        impressions=base * 12,
                        views=base * 8,
                        likes=base * 2,
                        comments=base // 5,
                        shares=base // 6,
                        watch_time_seconds=base * 14,
                        ctr=0.08,
                        raw_payload={"mode": "synthetic"},
                    )
                )
            snapshots.append(snapshot)
        await self.db.flush()
        return snapshots

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
        for snapshot in snapshots:
            posts_by_date[str(snapshot.snapshot_date)] += snapshot.views
            by_platform[snapshot.platform] += snapshot.views
            by_format[snapshot.content_format] += snapshot.views
            if snapshot.topic:
                by_topic[snapshot.topic] += snapshot.views

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

        return AnalyticsOverviewResponse(
            summary=summary,
            posts_over_time=[ChartPoint(label=label, value=value) for label, value in posts_by_date.items()],
            engagement_by_platform=[ChartPoint(label=label, value=value) for label, value in by_platform.items()],
            format_performance=[ChartPoint(label=label, value=value) for label, value in by_format.items()],
            topic_performance=[ChartPoint(label=label, value=value) for label, value in by_topic.items()],
            publishing_funnel=publishing_funnel,
            source_reliability=source_reliability,
        )
