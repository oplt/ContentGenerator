from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ContentJobType(str, enum.Enum):
    TEXT = "text"
    VIDEO = "video"
    BOTH = "both"
    REVISION = "revision"


class ContentJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VideoStage(str, enum.Enum):
    QUEUED = "queued"
    RESEARCHING = "researching"
    SCRIPTING = "scripting"
    PLANNING = "planning"
    COLLECTING_ASSETS = "collecting_assets"
    GENERATING_VOICE = "generating_voice"
    CAPTIONING = "captioning"
    RENDERING = "rendering"
    PACKAGING = "packaging"
    FAILED = "failed"
    COMPLETED = "completed"


class GeneratedAssetType(str, enum.Enum):
    PLANNER_STAGE = "planner_stage"
    WRITER_STAGE = "writer_stage"
    REVIEWER_STAGE = "reviewer_stage"
    FORMATTER_STAGE = "formatter_stage"
    RENDERER_INPUT = "renderer_input"
    TEXT_VARIANT = "text_variant"
    RESEARCH_DIGEST = "research_digest"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    VOICEOVER = "voiceover"
    CAPTION = "caption"
    VIDEO = "video"
    PREVIEW_CLIP = "preview_clip"
    THUMBNAIL = "thumbnail"
    METADATA = "metadata"
    THREAD = "thread"
    HASHTAG_PACK = "hashtag_pack"
    IMAGE_CAPTION = "image_caption"
    CAROUSEL_SLIDES = "carousel_slides"
    COVER_COPY = "cover_copy"
    HOOK = "hook"
    SHOT_LIST = "shot_list"
    SUBTITLE = "subtitle"
    ONSCREEN_TEXT = "onscreen_text"
    TITLE_VARIANTS = "title_variants"
    DESCRIPTION = "description"
    TAGS = "tags"
    BEAT_SHEET = "beat_sheet"
    FACT_CHECKLIST = "fact_checklist"
    ATTRIBUTION_LIST = "attribution_list"
    POLICY_FLAGS = "policy_flags"
    BRAND_VOICE_REPORT = "brand_voice_report"
    ORIGINALITY_REPORT = "originality_report"


class GeneratedAssetGroupStatus(str, enum.Enum):
    CREATED = "created"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    REGENERATED = "regenerated"
    PUBLISHED = "published"


class ContentJob(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "content_jobs"
    __table_args__ = (
        Index("ix_content_jobs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_content_jobs_content_plan_id", "content_plan_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    content_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False
    )
    revision_of_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="SET NULL"), nullable=True
    )
    job_type: Mapped[ContentJobType] = mapped_column(String(32), nullable=False, default="text")
    status: Mapped[ContentJobStatus] = mapped_column(String(32), nullable=False, default="queued")
    stage: Mapped[VideoStage] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    grounding_bundle: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    provider_metadata: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "content_revisions"
    __table_args__ = (Index("ix_content_revisions_content_job_id", "content_job_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    content_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    source_channel: Mapped[str] = mapped_column(String(64), nullable=False, default="dashboard")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)


class GeneratedAssetGroup(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "generated_asset_groups"
    __table_args__ = (
        Index("ix_generated_asset_groups_tenant_id_status", "tenant_id", "status"),
        Index("ix_generated_asset_groups_content_job_id", "content_job_id"),
        Index("ix_generated_asset_groups_content_plan_id", "content_plan_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    content_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    content_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_plans.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[GeneratedAssetGroupStatus] = mapped_column(
        String(32), nullable=False, default=GeneratedAssetGroupStatus.CREATED.value
    )
    platform_targets: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    asset_types: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    generation_trace: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    quality_report: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


class GeneratedAsset(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "generated_assets"
    __table_args__ = (
        Index("ix_generated_assets_content_job_id", "content_job_id"),
        Index("ix_generated_assets_asset_group_id", "asset_group_id"),
        Index("ix_generated_assets_tenant_id_asset_type", "tenant_id", "asset_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    asset_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("generated_asset_groups.id", ondelete="SET NULL"), nullable=True
    )
    content_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[GeneratedAssetType] = mapped_column(String(64), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    variant_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    public_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="text/plain")
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_metadata: Mapped[dict[str, str]] = mapped_column("metadata", default=dict, nullable=False)
    source_trace: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
