from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import literal_column

from backend.modules.analytics.models import AnalyticsSnapshot, PostAnalytics, TemplatePerformance
from backend.modules.content_generation.models import ContentJob
from backend.modules.content_strategy.models import ContentPlan
from backend.modules.publishing.models import PublishedPost, PublishingJob
from backend.modules.story_intelligence.models import StoryCluster


@dataclass(frozen=True)
class PostSyncContext:
    """Joined publish → content → plan → cluster context for one published post."""

    post: PublishedPost
    publish_job_id: UUID
    tone: str
    content_vertical: str


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

    async def list_snapshots(
        self,
        tenant_id: UUID,
        limit: int = 365,
        *,
        social_account_id: UUID | None = None,
    ) -> list[AnalyticsSnapshot]:
        stmt = select(AnalyticsSnapshot).where(AnalyticsSnapshot.tenant_id == tenant_id)
        if social_account_id is not None:
            stmt = stmt.where(AnalyticsSnapshot.social_account_id == social_account_id)
        result = await self.db.execute(
            stmt.order_by(AnalyticsSnapshot.snapshot_date.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_snapshot_for_post(
        self, published_post_id: UUID, snapshot_date: date
    ) -> AnalyticsSnapshot | None:
        snapshots = await self.get_snapshots_for_posts([published_post_id], snapshot_date)
        return snapshots.get(published_post_id)

    async def get_snapshots_for_posts(
        self, published_post_ids: list[UUID], snapshot_date: date
    ) -> dict[UUID, AnalyticsSnapshot]:
        if not published_post_ids:
            return {}
        result = await self.db.execute(
            select(AnalyticsSnapshot).where(
                AnalyticsSnapshot.published_post_id.in_(published_post_ids),
                AnalyticsSnapshot.snapshot_date == snapshot_date,
            )
        )
        return {row.published_post_id: row for row in result.scalars().all()}

    async def list_post_sync_contexts(
        self, tenant_id: UUID, limit: int = 100
    ) -> list[PostSyncContext]:
        """
        Load published posts with tone/vertical via one tenant-scoped join.

        Outer-joins keep posts syncable when plan/cluster links are missing.
        """
        tone_col = func.coalesce(ContentPlan.tone, "authoritative").label("tone")
        vertical_col = func.coalesce(StoryCluster.content_vertical, "general").label(
            "content_vertical"
        )
        result = await self.db.execute(
            select(PublishedPost, PublishingJob.id, tone_col, vertical_col)
            .join(PublishingJob, PublishingJob.id == PublishedPost.publishing_job_id)
            .outerjoin(ContentJob, ContentJob.id == PublishingJob.content_job_id)
            .outerjoin(
                ContentPlan,
                (ContentPlan.id == ContentJob.content_plan_id) & ContentPlan.deleted_at.is_(None),
            )
            .outerjoin(
                StoryCluster,
                (StoryCluster.id == ContentPlan.story_cluster_id)
                & StoryCluster.deleted_at.is_(None),
            )
            .where(
                PublishedPost.tenant_id == tenant_id,
                PublishingJob.tenant_id == tenant_id,
            )
            .order_by(PublishedPost.created_at.desc())
            .limit(limit)
        )
        contexts: list[PostSyncContext] = []
        for post, publish_job_id, tone, content_vertical in result.all():
            contexts.append(
                PostSyncContext(
                    post=post,
                    publish_job_id=publish_job_id,
                    tone=str(tone or "authoritative"),
                    content_vertical=str(content_vertical or "general"),
                )
            )
        return contexts

    async def upsert_snapshot(
        self,
        *,
        tenant_id: UUID,
        published_post_id: UUID,
        platform: str,
        snapshot_date: date,
        topic: str | None,
        content_format: str,
        impressions: int,
        views: int,
        likes: int,
        comments: int,
        shares: int,
        watch_time_seconds: int,
        ctr: float | None,
        sync_source: str,
        raw_payload: dict[str, str],
        social_account_id: UUID | None = None,
        account_label: str | None = None,
    ) -> tuple[AnalyticsSnapshot, bool]:
        """
        Insert or update daily snapshot on unique (published_post_id, snapshot_date).

        Returns (snapshot, was_inserted). Concurrent syncs converge on one row.
        """
        snapshot_id = uuid4()
        insert_stmt = insert(AnalyticsSnapshot)
        stmt: Any = (
            insert_stmt.values(
                id=snapshot_id,
                tenant_id=tenant_id,
                published_post_id=published_post_id,
                social_account_id=social_account_id,
                account_label=account_label,
                platform=platform,
                snapshot_date=snapshot_date,
                topic=topic,
                content_format=content_format,
                impressions=impressions,
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                watch_time_seconds=watch_time_seconds,
                ctr=ctr,
                sync_source=sync_source,
                raw_payload=raw_payload or {},
            )
            .on_conflict_do_update(
                constraint="uq_analytics_snapshots_published_post_id_snapshot_date",
                set_={
                    "platform": insert_stmt.excluded.platform,
                    "social_account_id": insert_stmt.excluded.social_account_id,
                    "account_label": insert_stmt.excluded.account_label,
                    "topic": insert_stmt.excluded.topic,
                    "content_format": insert_stmt.excluded.content_format,
                    "impressions": insert_stmt.excluded.impressions,
                    "views": insert_stmt.excluded.views,
                    "likes": insert_stmt.excluded.likes,
                    "comments": insert_stmt.excluded.comments,
                    "shares": insert_stmt.excluded.shares,
                    "watch_time_seconds": insert_stmt.excluded.watch_time_seconds,
                    "ctr": insert_stmt.excluded.ctr,
                    "sync_source": insert_stmt.excluded.sync_source,
                    "raw_payload": insert_stmt.excluded.raw_payload,
                },
            )
            .returning(AnalyticsSnapshot, literal_column("(xmax = 0)").label("was_inserted"))
        )
        result = await self.db.execute(stmt)
        row = result.one()
        snapshot = row[0]
        was_inserted = bool(row[1])
        return snapshot, was_inserted

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

    async def apply_template_performance_sample(
        self,
        *,
        tenant_id: UUID,
        platform: str,
        tone: str,
        content_vertical: str,
        impressions: int,
        likes: int,
        comments: int,
        shares: int,
        ctr: float,
        engagement_score: float,
        computed_at: datetime,
    ) -> TemplatePerformance:
        """
        Atomically fold one sample into TemplatePerformance.

        Uses ON CONFLICT running-average math so concurrent syncs cannot
        double-apply via read-modify-write races.
        """
        tp_table = TemplatePerformance.__table__
        insert_stmt = insert(TemplatePerformance)
        excluded = insert_stmt.excluded
        stmt = (
            insert_stmt.values(
                id=uuid4(),
                tenant_id=tenant_id,
                platform=platform,
                tone=tone,
                content_vertical=content_vertical,
                sample_count=1,
                avg_impressions=float(impressions),
                avg_likes=float(likes),
                avg_comments=float(comments),
                avg_shares=float(shares),
                avg_ctr=float(ctr),
                approve_rate=0.0,
                revise_rate=0.0,
                reject_rate=0.0,
                engagement_score=engagement_score,
                last_computed_at=computed_at,
            )
            .on_conflict_do_update(
                constraint="uq_template_performance_tenant_platform_tone_vertical",
                set_={
                    "avg_impressions": (
                        (tp_table.c.avg_impressions * tp_table.c.sample_count)
                        + excluded.avg_impressions
                    )
                    / (tp_table.c.sample_count + 1),
                    "avg_likes": (
                        (tp_table.c.avg_likes * tp_table.c.sample_count) + excluded.avg_likes
                    )
                    / (tp_table.c.sample_count + 1),
                    "avg_comments": (
                        (tp_table.c.avg_comments * tp_table.c.sample_count)
                        + excluded.avg_comments
                    )
                    / (tp_table.c.sample_count + 1),
                    "avg_shares": (
                        (tp_table.c.avg_shares * tp_table.c.sample_count) + excluded.avg_shares
                    )
                    / (tp_table.c.sample_count + 1),
                    "avg_ctr": ((tp_table.c.avg_ctr * tp_table.c.sample_count) + excluded.avg_ctr)
                    / (tp_table.c.sample_count + 1),
                    "sample_count": tp_table.c.sample_count + 1,
                    "engagement_score": excluded.engagement_score,
                    "last_computed_at": excluded.last_computed_at,
                },
            )
            .returning(TemplatePerformance)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def list_template_performance(
        self, tenant_id: UUID, platform: str | None = None
    ) -> list[TemplatePerformance]:
        q = select(TemplatePerformance).where(TemplatePerformance.tenant_id == tenant_id)
        if platform:
            q = q.where(TemplatePerformance.platform == platform)
        q = q.order_by(TemplatePerformance.engagement_score.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())
