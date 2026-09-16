"""Persistent canonical chess catalog entities (provider-independent)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ChessGame(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Canonical historical / imported chess game (not a render job)."""

    __tablename__ = "chess_games"
    __table_args__ = (
        Index(
            "uq_chess_games_tenant_id_game_fingerprint",
            "tenant_id",
            "game_fingerprint",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_chess_games_tenant_id", "tenant_id"),
        Index("ix_chess_games_tenant_id_year", "tenant_id", "year"),
        Index("ix_chess_games_tenant_id_eco", "tenant_id", "eco"),
        Index("ix_chess_games_tenant_id_is_famous", "tenant_id", "is_famous"),
        Index("ix_chess_games_tenant_id_content_hash", "tenant_id", "content_hash"),
        Index("ix_chess_games_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_chess_games_tenant_id_result", "tenant_id", "result"),
        Index("ix_chess_games_tenant_id_provider", "tenant_id", "source_provider"),
        Index(
            "uq_chess_games_tenant_provider_external",
            "tenant_id",
            "source_provider",
            "source_external_id",
            unique=True,
            postgresql_where=text("source_external_id IS NOT NULL AND deleted_at IS NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    white_player: Mapped[str | None] = mapped_column(String(255), nullable=True)
    black_player: Mapped[str | None] = mapped_column(String(255), nullable=True)
    white_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    event: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    round: Mapped[str | None] = mapped_column(String(64), nullable=True)
    game_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    result: Mapped[str | None] = mapped_column(String(16), nullable=True)

    eco: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opening: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variation: Mapped[str | None] = mapped_column(String(255), nullable=True)

    starting_fen: Mapped[str] = mapped_column(String(128), nullable=False)
    final_fen: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_pgn: Mapped[str] = mapped_column(Text, nullable=False)
    move_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    game_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    is_famous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    famous_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    historical_tags: Mapped[list[str]] = mapped_column(default=list, nullable=False)


class ChessGameSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance row: many providers may point at one canonical ChessGame."""

    __tablename__ = "chess_game_sources"
    __table_args__ = (
        Index("ix_chess_game_sources_tenant_id", "tenant_id"),
        Index("ix_chess_game_sources_chess_game_id", "chess_game_id"),
        Index(
            "uq_chess_game_sources_tenant_provider_external",
            "tenant_id",
            "provider",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "ix_chess_game_sources_game_provider_batch",
            "chess_game_id",
            "provider",
            "import_batch_id",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ChessPuzzle(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Canonical chess puzzle (provider-independent)."""

    __tablename__ = "chess_puzzles"
    __table_args__ = (
        Index(
            "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
            "tenant_id",
            "puzzle_fingerprint",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_chess_puzzles_tenant_id", "tenant_id"),
        Index("ix_chess_puzzles_tenant_id_rating", "tenant_id", "rating"),
        Index("ix_chess_puzzles_tenant_id_popularity", "tenant_id", "popularity"),
        Index("ix_chess_puzzles_tenant_id_provider", "tenant_id", "provider"),
        Index("ix_chess_puzzles_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_chess_puzzles_tenant_id_import_batch", "tenant_id", "import_batch_id"),
        Index(
            "uq_chess_puzzles_tenant_provider_external",
            "tenant_id",
            "provider",
            "external_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)

    starting_fen: Mapped[str] = mapped_column(String(128), nullable=False)
    solution_moves_uci: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    solution_moves_san: Mapped[list[str]] = mapped_column(default=list, nullable=False)

    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_deviation: Mapped[float | None] = mapped_column(Float, nullable=True)
    popularity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    play_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    themes: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    opening_tags: Mapped[list[str]] = mapped_column(default=list, nullable=False)

    source_game_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_game_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    puzzle_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ChessAnalysisJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChessAnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Background Stockfish analysis run for one catalog game."""

    __tablename__ = "chess_analysis_jobs"
    __table_args__ = (
        Index("ix_chess_analysis_jobs_tenant_id", "tenant_id"),
        Index("ix_chess_analysis_jobs_chess_game_id", "chess_game_id"),
        Index("ix_chess_analysis_jobs_tenant_id_status", "tenant_id", "status"),
        Index(
            "ix_chess_analysis_jobs_tenant_game_created",
            "tenant_id",
            "chess_game_id",
            "created_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChessAnalysisJobStatus.QUEUED.value
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_limit_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    hash_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    threads: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    engine_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analysis_settings: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    ply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

class ChessPositionAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-ply engine snapshot (White POV scores — see EngineScore docs)."""

    __tablename__ = "chess_position_analyses"
    __table_args__ = (
        UniqueConstraint(
            "analysis_job_id",
            "ply",
            name="uq_chess_position_analyses_job_ply",
        ),
        Index("ix_chess_position_analyses_job_id", "analysis_job_id"),
        Index("ix_chess_position_analyses_chess_game_id", "chess_game_id"),
        Index("ix_chess_position_analyses_tenant_game", "tenant_id", "chess_game_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(String(128), nullable=False)

    evaluation_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mate_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_before_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mate_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_after_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mate_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evaluation_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)

    best_move_uci: Mapped[str | None] = mapped_column(String(16), nullable=True)
    best_move_san: Mapped[str | None] = mapped_column(String(32), nullable=True)
    played_move_uci: Mapped[str] = mapped_column(String(16), nullable=False)
    played_move_san: Mapped[str] = mapped_column(String(32), nullable=False)

    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nodes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engine_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analysis_settings: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)


class ChessCriticalMoment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Heuristic critical moment derived from engine facts (not LLM editorial)."""

    __tablename__ = "chess_critical_moments"
    __table_args__ = (
        Index("ix_chess_critical_moments_job_id", "analysis_job_id"),
        Index("ix_chess_critical_moments_chess_game_id", "chess_game_id"),
        Index("ix_chess_critical_moments_tenant_game", "tenant_id", "chess_game_id"),
        Index(
            "ix_chess_critical_moments_job_ply_class",
            "analysis_job_id",
            "ply",
            "classification",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_facts: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    # Template sentence from heuristics — not LLM editorial prose.
    heuristic_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Reserved for later human/LLM editorial layer (Phase 18+).
    editorial_description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChessTacticalPattern(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Geometric/material tactical pattern with confidence + detection method."""

    __tablename__ = "chess_tactical_patterns"
    __table_args__ = (
        Index("ix_chess_tactical_patterns_job_id", "analysis_job_id"),
        Index("ix_chess_tactical_patterns_chess_game_id", "chess_game_id"),
        Index("ix_chess_tactical_patterns_tenant_game", "tenant_id", "chess_game_id"),
        Index(
            "ix_chess_tactical_patterns_job_ply_pattern",
            "analysis_job_id",
            "ply",
            "pattern",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_analysis_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    pattern: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detection_method: Mapped[str] = mapped_column(String(64), nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)


class ChessContentOpportunityScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted transparent content-opportunity score (components always explain score)."""

    __tablename__ = "chess_content_opportunity_scores"
    __table_args__ = (
        Index("ix_chess_content_opp_tenant_game", "tenant_id", "chess_game_id"),
        Index("ix_chess_content_opp_analysis_job_id", "analysis_job_id"),
        Index("ix_chess_content_opp_tenant_score", "tenant_id", "score"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    chess_game_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("chess_games.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_job_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("chess_analysis_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    components: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    reasons: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(64), nullable=False, default="content_opportunity_v1")
