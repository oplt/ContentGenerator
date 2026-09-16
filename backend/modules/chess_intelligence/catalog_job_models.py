"""Durable async catalog jobs (imports, enrichment, provider sync) — Phase 24."""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChessCatalogJobKind(str, enum.Enum):
    PGN_IMPORT = "pgn_import"
    PUZZLE_IMPORT = "puzzle_import"
    ENRICH_FAMOUS = "enrich_famous"
    EXTRACT_CRITICAL_MOMENTS = "extract_critical_moments"
    PROVIDER_SYNC = "provider_sync"


class ChessCatalogJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChessCatalogJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Long-running chess catalog work with persisted progress (Celery)."""

    __tablename__ = "chess_catalog_jobs"
    __table_args__ = (
        Index("ix_chess_catalog_jobs_tenant_id", "tenant_id"),
        Index("ix_chess_catalog_jobs_tenant_id_status", "tenant_id", "status"),
        Index("ix_chess_catalog_jobs_tenant_id_kind", "tenant_id", "kind"),
        Index("ix_chess_catalog_jobs_tenant_created", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChessCatalogJobStatus.QUEUED.value
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
