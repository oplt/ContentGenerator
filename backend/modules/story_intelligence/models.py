from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ClusterStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    MERGED = "merged"


class TrendWorkflowState(str, enum.Enum):
    NEW = "new"
    QUEUED_FOR_REVIEW = "queued_for_review"
    APPROVED_TOPIC = "approved_topic"
    BRIEF_READY = "brief_ready"
    ASSET_GENERATION = "asset_generation"
    ASSET_REVIEW = "asset_review"
    PUBLISH_READY = "publish_ready"
    PUBLISHED = "published"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RiskLevel(str, enum.Enum):
    SAFE = "safe"
    SENSITIVE = "sensitive"   # Requires brief approval before generation
    RISKY = "risky"            # Requires multi-source Tier 1 confirmation
    UNSAFE = "unsafe"          # Blocked — requires manual review


class ClusterBlockReason(str, enum.Enum):
    UNSAFE_CONTENT = "unsafe_content"
    INSUFFICIENT_TIER1_CONFIRMATION = "insufficient_tier1_confirmation"
    CONTRADICTORY_CLAIMS = "contradictory_claims"
    MANUAL_BLOCK = "manual_block"


class TrendCandidateStatus(str, enum.Enum):
    NEW = "new"
    QUEUED_FOR_REVIEW = "queued_for_review"
    APPROVED_TOPIC = "approved_topic"
    REJECTED_TOPIC = "rejected_topic"
    EXPIRED = "expired"


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
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keywords: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    topic_tags: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    entities: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(default=list, nullable=False)
    # Enrichment fields populated by the extractor role (Step 6)
    content_vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    source_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, default="signal"
    )  # inherited from Source at fetch time
    geography: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    claims: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    risk_flags: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    worthiness_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    explainability: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class StoryCluster(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "story_clusters"
    __table_args__ = (
        Index("ix_story_clusters_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_story_clusters_tenant_id_worthy_for_content", "tenant_id", "worthy_for_content"),
        Index("ix_story_clusters_tenant_id_vertical_risk", "tenant_id", "content_vertical", "risk_level"),
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
    workflow_state: Mapped[TrendWorkflowState] = mapped_column(
        String(32), nullable=False, default=TrendWorkflowState.NEW.value
    )
    # Content vertical — drives risk policy and source confirmation requirements
    content_vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    # Risk flags — list of strings explaining why risk_level was set
    risk_flags: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    # Number of confirmed Tier 1 sources covering this cluster
    tier1_sources_confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Block reason if cluster is UNSAFE or held for confirmation
    block_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Whether cluster is waiting for more Tier 1 confirmation
    awaiting_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Representative semantic embedding for cluster (floats, same dims as NormalizedArticle.embedding)
    embedding: Mapped[list[float]] = mapped_column(default=list, nullable=False)
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
    velocity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cross_source_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Step 7: enriched scoring dimensions
    audience_fit_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    monetization_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_penalty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    explanation: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class TrendCandidate(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "trend_candidates"
    __table_args__ = (
        UniqueConstraint("story_cluster_id", "date_bucket", name="uq_trend_candidates_story_cluster_id_date_bucket"),
        Index("ix_trend_candidates_tenant_id_status_date_bucket", "tenant_id", "status", "date_bucket"),
        Index("ix_trend_candidates_tenant_id_final_score", "tenant_id", "final_score"),
        Index("ix_trend_candidates_story_cluster_id", "story_cluster_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    story_cluster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False
    )
    date_bucket: Mapped[date] = mapped_column(nullable=False)
    primary_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    subtopics: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    supporting_item_ids: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    evidence_links: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    extracted_claims: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    cross_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_mix: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    velocity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    recency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    audience_fit_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    monetization_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[TrendCandidateStatus] = mapped_column(
        String(32), nullable=False, default=TrendCandidateStatus.NEW.value
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score_explanation: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
