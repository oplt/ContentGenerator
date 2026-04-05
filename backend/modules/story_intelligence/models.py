from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ClusterStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    MERGED = "merged"


class RiskLevel(str, enum.Enum):
    SAFE = "safe"
    RISKY = "risky"
    UNSAFE = "unsafe"


class NormalizedArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "normalized_articles"
    __table_args__ = (
        UniqueConstraint("raw_article_id", name="uq_normalized_articles_raw_article_id"),
        Index("ix_normalized_articles_tenant_id_published_at", "tenant_id", "published_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    raw_article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("raw_articles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="en")
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    keywords: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    topic_tags: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    entities: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    embedding: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    worthiness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    explainability: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class StoryCluster(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "story_clusters"
    __table_args__ = (
        Index("ix_story_clusters_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_story_clusters_tenant_id_worthy_for_content", "tenant_id", "worthy_for_content"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    primary_topic: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[ClusterStatus] = mapped_column(String(32), nullable=False, default="active")
    representative_article_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("normalized_articles.id", ondelete="SET NULL"), nullable=True
    )
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trend_direction: Mapped[str] = mapped_column(String(32), nullable=False, default="flat")
    worthy_for_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_level: Mapped[RiskLevel] = mapped_column(String(32), nullable=False, default="safe")
    explainability: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class StoryClusterArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "story_cluster_articles"
    __table_args__ = (
        UniqueConstraint(
            "story_cluster_id",
            "normalized_article_id",
            name="uq_sca_cluster_article",
        ),
    )

    story_cluster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False
    )
    normalized_article_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("normalized_articles.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TrendScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trend_scores"
    __table_args__ = (
        Index("ix_trend_scores_story_cluster_id_created_at", "story_cluster_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    story_cluster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    worthiness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    calculated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    explanation: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
