from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AnalyticsSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "published_post_id",
            "snapshot_date",
            name="uq_analytics_snapshots_published_post_id_snapshot_date",
        ),
        Index("ix_analytics_snapshots_tenant_id_snapshot_date", "tenant_id", "snapshot_date"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    published_post_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("published_posts.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(nullable=False)
    topic: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_format: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    # Source of this snapshot: "synthetic" | "x_api" | "instagram_api" | "youtube_api"
    sync_source: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")


class TemplatePerformance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Aggregate performance per (tenant, platform, tone, content_vertical) tuple.

    Updated after each analytics sync. Used by OptimizationService to recommend
    content parameters based on historical engagement data.
    """
    __tablename__ = "template_performance"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "platform", "tone", "content_vertical",
            name="uq_template_performance_tenant_platform_tone_vertical",
        ),
        Index("ix_template_performance_tenant_id_platform", "tenant_id", "platform"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    tone: Mapped[str] = mapped_column(String(128), nullable=False, default="authoritative")
    content_vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general")

    # Aggregate engagement metrics
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_impressions: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_likes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_comments: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_shares: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Approval outcome rates (from ApprovalService._record_preference)
    approve_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    revise_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reject_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Composite engagement score (0–1) used by OptimizationService
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PostAnalytics(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "post_analytics"
    __table_args__ = (
        UniqueConstraint("publish_job_id", "fetched_at", name="uq_post_analytics_publish_job_id_fetched_at"),
        Index("ix_post_analytics_tenant_id_fetched_at", "tenant_id", "fetched_at"),
        Index("ix_post_analytics_publish_job_id", "publish_job_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    publish_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="CASCADE"), nullable=False
    )
    published_post_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("published_posts.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    saves: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_time: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_watch_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    retention: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    profile_visits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    follows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_metrics: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
