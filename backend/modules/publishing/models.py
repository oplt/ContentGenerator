from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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
    QUARANTINED = "quarantined"


class PublishingJobStatus(str, enum.Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    CLAIMED = "claimed"          # Locked by a worker — prevents double-publish
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_DRY_RUN = "succeeded_dry_run"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD = "dead"                # Max retries exceeded
    MANUAL_REQUIRED = "manual_required"


class PublishingAttemptStatus(str, enum.Enum):
    PREPARED = "prepared"  # Durable before provider I/O
    SUCCEEDED = "succeeded"
    FAILED_TRANSIENT = "failed_transient"
    FAILED_PERMANENT = "failed_permanent"
    AMBIGUOUS = "ambiguous"  # Timeout / unknown after possible side effect


class PublishedPostStatus(str, enum.Enum):
    LIVE = "live"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class ConnectedAccountStatus(str, enum.Enum):
    ACTIVE = "active"
    NEEDS_REAUTH = "needs_reauth"
    DISCONNECTED = "disconnected"
    QUARANTINED = "quarantined"


class SocialAccount(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    """Canonical publishable account identity (T4.1).

    ConnectedAccount is a legacy dual-write projection. Prefer this model for all
    new reads/writes. ``account_external_id`` is required for non-deleted rows after
    consolidation (minted ``legacy:*`` when provider id is unknown).
    """

    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "account_external_id",
            name="uq_social_accounts_tenant_id_platform_account_external_id",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_social_accounts_tenant_id_id"),
        Index("ix_social_accounts_tenant_id_platform", "tenant_id", "platform"),
        Index(
            "ix_social_accounts_tenant_id_platform_status",
            "tenant_id",
            "platform",
            "status",
        ),
        Index("ix_social_accounts_legacy_connected_account_id", "legacy_connected_account_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    account_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    auth_type: Mapped[str] = mapped_column(String(64), nullable=False, default="oauth")
    capability_flags: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    account_metadata: Mapped[dict[str, str]] = mapped_column("metadata", default=dict, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True
    )  # Lineage only; no FK to avoid social↔connected cycle.
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConnectedAccount(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    """Legacy projection of SocialAccount (dual-write; do not use as identity)."""

    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "account_name",
            name="uq_connected_accounts_tenant_id_platform_account_name",
        ),
        Index("ix_connected_accounts_tenant_id_platform_status", "tenant_id", "platform", "status"),
        Index("ix_connected_accounts_social_account_id", "social_account_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(64), nullable=False, default="oauth")
    credential_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    account_metadata: Mapped[dict[str, object]] = mapped_column("metadata", default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ConnectedAccountStatus.ACTIVE.value
    )


class SocialAccountToken(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Credential binding for a SocialAccount. At most one active binding per account."""

    __tablename__ = "social_account_tokens"
    __table_args__ = (
        Index("ix_social_account_tokens_social_account_id", "social_account_id"),
        Index(
            "uq_social_account_tokens_active_binding",
            "social_account_id",
            unique=True,
            postgresql_where=text("is_active IS true AND deleted_at IS NULL"),
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    binding_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PublishingJob(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "publishing_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publishing_jobs_idempotency_key"),
        Index("ix_publishing_jobs_tenant_id_status", "tenant_id", "status"),
        Index("ix_publishing_jobs_status_retry_count", "status", "retry_count"),
        Index("ix_publishing_jobs_status_dead_lettered_at", "status", "dead_lettered_at"),
        Index("ix_publishing_jobs_status_claim_expires_at", "status", "claim_expires_at"),
        Index("ix_publishing_jobs_content_variant_id", "content_variant_id"),
        Index(
            "ix_publishing_jobs_tenant_social_account_created_at",
            "tenant_id",
            "social_account_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_publishing_jobs_approval_request_id",
            "approval_request_id",
            postgresql_where=text("approval_request_id IS NOT NULL"),
        ),
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
    content_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_variants.id", ondelete="SET NULL"), nullable=True
    )
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="stub")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Race-condition safety: claimed_at + worker_id set atomically via FOR UPDATE SKIP LOCKED
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_post_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    current_attempt_key: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PublishingAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable publish attempt boundary committed before provider I/O."""

    __tablename__ = "publishing_attempts"
    __table_args__ = (
        UniqueConstraint("attempt_key", name="uq_publishing_attempts_attempt_key"),
        UniqueConstraint(
            "publishing_job_id",
            "attempt_number",
            name="uq_publishing_attempts_job_id_attempt_number",
        ),
        Index("ix_publishing_attempts_publishing_job_id_status", "publishing_job_id", "status"),
    )

    publishing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PublishingAttemptStatus.PREPARED.value
    )
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_post_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    provider_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PublishedPost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "published_posts"
    __table_args__ = (
        Index("ix_published_posts_tenant_id_platform", "tenant_id", "platform"),
        Index("ix_published_posts_tenant_id_social_account_id", "tenant_id", "social_account_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    social_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    publishing_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publishing_jobs.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    post_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    external_post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    analytics_sync_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # Immutable account attribution surviving disconnect/delete.
    account_display_snapshot: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
