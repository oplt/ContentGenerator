from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
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
