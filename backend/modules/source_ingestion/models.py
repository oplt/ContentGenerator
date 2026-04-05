from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class SourceType(str, enum.Enum):
    RSS = "rss"
    SITEMAP = "sitemap"
    WEB = "web"
    API = "api"


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class FetchRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Source(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_sources_tenant_id_name"),
        Index("ix_sources_tenant_id_active", "tenant_id", "active"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(String(32), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    parser_type: Mapped[str] = mapped_column(String(64), nullable=False, default="auto")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    config: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    polling_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    robots_respected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    circuit_state: Mapped[CircuitState] = mapped_column(
        String(32), nullable=False, default=CircuitState.CLOSED.value
    )
    negative_cache_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_cache_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)


class SourceFetchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_fetch_runs"
    __table_args__ = (Index("ix_source_fetch_runs_source_id_created_at", "source_id", "created_at"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[FetchRunStatus] = mapped_column(String(32), nullable=False, default="queued")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    articles_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_articles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_metadata: Mapped[dict[str, str]] = mapped_column("metadata", default=dict, nullable=False)


class RawArticle(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "raw_articles"
    __table_args__ = (
        Index("ix_raw_articles_tenant_id_published_at", "tenant_id", "published_at"),
        Index("ix_raw_articles_source_id_canonical_url", "source_id", "canonical_url"),
        UniqueConstraint("tenant_id", "content_hash", name="uq_raw_articles_tenant_id_content_hash"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    fetch_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_fetch_runs.id", ondelete="SET NULL"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_metadata: Mapped[dict[str, str]] = mapped_column("metadata", default=dict, nullable=False)
