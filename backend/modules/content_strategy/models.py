from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ContentPlanStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    APPROVAL_PENDING = "approval_pending"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class ContentFormat(str, enum.Enum):
    TEXT = "text"
    VIDEO = "video"
    BOTH = "both"


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_brands_tenant_id_name"),
        Index("ix_brands_tenant_id_niche", "tenant_id", "niche"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str] = mapped_column(String(128), nullable=False, default="general")
    style_guide: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    allowed_topics: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    blocked_topics: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    target_platforms: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    risk_policy: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    posting_policy: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


class BrandProfile(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "brand_profiles"
    __table_args__ = (
        Index("ix_brand_profiles_tenant_id", "tenant_id"),
        Index("ix_brand_profiles_brand_id", "brand_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str] = mapped_column(String(128), nullable=False, default="general")
    tone: Mapped[str] = mapped_column(String(128), nullable=False, default="authoritative")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="General social audience")
    voice_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_platforms: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    default_cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags_strategy: Mapped[str] = mapped_column(String(128), nullable=False, default="balanced")
    risk_tolerance: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    require_whatsapp_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    guardrails: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    visual_style: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class BrandSourcePolicy(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "brand_source_policies"
    __table_args__ = (
        UniqueConstraint("brand_id", "source_id", name="uq_brand_source_policies_brand_id_source_id"),
        Index("ix_brand_source_policies_brand_id_enabled", "brand_id", "enabled"),
        Index("ix_brand_source_policies_source_id_enabled", "source_id", "enabled"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    policy_metadata: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


class ContentPlan(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "content_plans"
    __table_args__ = (
        Index("ix_content_plans_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_content_plans_story_cluster_id", "story_cluster_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    story_cluster_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("story_clusters.id", ondelete="CASCADE"), nullable=False
    )
    brand_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brand_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ContentPlanStatus] = mapped_column(String(32), nullable=False, default="draft")
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="generate")
    content_format: Mapped[ContentFormat] = mapped_column(String(32), nullable=False, default="text")
    target_platforms: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    tone: Mapped[str] = mapped_column(String(128), nullable=False, default="authoritative")
    urgency: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    risk_flags: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    recommended_cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashtags_strategy: Mapped[str] = mapped_column(String(128), nullable=False, default="balanced")
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    safe_to_publish: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    policy_trace: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
