from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class BriefStatus(str, enum.Enum):
    PENDING = "pending"        # Queued for generation
    GENERATING = "generating"  # LLM is running
    READY = "ready"            # Generated, awaiting approval
    APPROVED = "approved"      # Topic brief approved — proceed to content
    REJECTED = "rejected"      # Operator rejected — do not proceed
    EXPIRED = "expired"        # Not acted on within TTL


class EditorialBrief(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    """
    Summarises the editorial angle and instructions for a story cluster.

    Lifecycle:
        PENDING → GENERATING → READY → APPROVED → (content generation triggered)
                                      → REJECTED → (cluster held)
                                      → EXPIRED  → (cluster held)
    """
    __tablename__ = "editorial_briefs"
    __table_args__ = (
        UniqueConstraint("story_cluster_id", name="uq_editorial_briefs_story_cluster_id"),
        Index("ix_editorial_briefs_tenant_id_status", "tenant_id", "status"),
        Index("ix_editorial_briefs_story_cluster_id", "story_cluster_id"),
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

    status: Mapped[BriefStatus] = mapped_column(String(32), nullable=False, default=BriefStatus.PENDING.value)

    # Core brief fields (populated during GENERATING → READY transition)
    headline: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    why_now: Mapped[str] = mapped_column(Text, nullable=False, default="")
    angle: Mapped[str] = mapped_column(Text, nullable=False, default="")
    talking_points: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    recommended_format: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    target_platforms: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    evidence_links: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    audience_segment: Mapped[str] = mapped_column(String(255), nullable=False, default="general social audience")
    platform_recommendations: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    tone_guidance: Mapped[str] = mapped_column(String(128), nullable=False, default="authoritative")
    cta_strategy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    caveats: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    suggested_formats: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    content_vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    risk_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="safe")
    rewrite_context: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)

    # Operator feedback on approval/rejection
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Expiry — brief must be acted on within this window
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Telegram short-code for the approval flow (set when brief card is sent)
    telegram_short_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Telegram message_id of the brief card — stored so it can be edited in-place after approve/reject
    telegram_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # LLM explainability / raw output
    generation_trace: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
