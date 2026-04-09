from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TrendingRepo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Snapshot of a trending GitHub repository for a given period and date."""

    __tablename__ = "trending_repos"

    # Tenant scope
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    # Snapshot context
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # daily | weekly | monthly
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    # GitHub repo identity
    github_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)          # owner/repo
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str] = mapped_column(String(512), nullable=False)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)           # JSON list

    # Stats at snapshot time
    stars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forks_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watchers_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issues_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stars gained within the period (proxy for trending velocity)
    stars_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Rank within this snapshot (1 = most trending)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    # LLM-generated product ideas (list of idea dicts)
    product_ideas: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ideas_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_trending_repos_tenant_period_date", "tenant_id", "period", "snapshot_date"),
        Index("ix_trending_repos_tenant_date", "tenant_id", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return f"<TrendingRepo {self.name} period={self.period} rank={self.rank}>"
