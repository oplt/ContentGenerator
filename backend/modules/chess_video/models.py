from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChessVideoJobStatus(str, enum.Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    PREPARING = "preparing"
    RENDERING = "rendering"
    ENCODING = "encoding"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChessVideoInputFormat(str, enum.Enum):
    PGN = "pgn"
    SAN = "san"
    UCI = "uci"
    AUTO = "auto"


class ChessVideoOrientation(str, enum.Enum):
    WHITE = "white"
    BLACK = "black"


class ChessVideoRenderPreset(str, enum.Enum):
    ECONOMY_VERTICAL = "economy_vertical"
    SOCIAL_VERTICAL = "social_vertical"
    SQUARE = "square"
    HORIZONTAL = "horizontal"


class ChessVideoJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-scoped chess match video render job (standalone from ContentJob)."""

    __tablename__ = "chess_video_jobs"
    __table_args__ = (
        Index("ix_chess_video_jobs_tenant_id", "tenant_id"),
        Index("ix_chess_video_jobs_status", "status"),
        Index("ix_chess_video_jobs_created_at", "created_at"),
        Index("ix_chess_video_jobs_render_fingerprint", "render_fingerprint"),
        Index("ix_chess_video_jobs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_chess_video_jobs_tenant_id_status", "tenant_id", "status"),
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

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChessVideoJobStatus.QUEUED.value
    )
    stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChessVideoJobStatus.QUEUED.value
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    input_format: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ChessVideoInputFormat.AUTO.value
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_pgn: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    white_player: Mapped[str | None] = mapped_column(String(255), nullable=True)
    black_player: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event: Mapped[str | None] = mapped_column(String(255), nullable=True)
    game_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)

    starting_fen: Mapped[str | None] = mapped_column(String(128), nullable=True)
    move_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    orientation: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ChessVideoOrientation.WHITE.value
    )
    render_preset: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChessVideoRenderPreset.ECONOMY_VERTICAL.value
    )
    seconds_per_move: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    include_coordinates: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_move_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)

    renderer_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    render_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    video_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    video_public_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    thumbnail_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_public_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
