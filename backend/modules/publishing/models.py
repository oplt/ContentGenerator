from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class SocialPlatform(str, enum.Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    X = "x"
    BLUESKY = "bluesky"


class SocialAccountStatus(str, enum.Enum):
    CONNECTED = "connected"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"


class PublishingJobStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"


class PublishedPostStatus(str, enum.Enum):
    LIVE = "live"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class SocialAccount(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "account_external_id",
            name="uq_social_accounts_tenant_id_platform_account_external_id",
        ),
        Index("ix_social_accounts_tenant_id_platform", "tenant_id", "platform"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[SocialAccountStatus] = mapped_column(String(32), nullable=False, default="connected")
    capability_flags: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    account_metadata: Mapped[dict[str, str]] = mapped_column("metadata", default=dict, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialAccountToken(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "social_account_tokens"
    __table_args__ = (Index("ix_social_account_tokens_social_account_id", "social_account_id"),)

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PublishingJob(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publishing_jobs_idempotency_key"),
        Index("ix_publishing_jobs_tenant_id_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    content_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=False
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[SocialPlatform] = mapped_column(String(32), nullable=False)
    status: Mapped[PublishingJobStatus] = mapped_column(String(32), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="stub")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_post_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class PublishedPost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "published_posts"
    __table_args__ = (Index("ix_published_posts_tenant_id_platform", "tenant_id", "platform"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    publishing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[SocialPlatform] = mapped_column(String(32), nullable=False)
    post_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[PublishedPostStatus] = mapped_column(String(32), nullable=False, default="scheduled")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    analytics_sync_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
