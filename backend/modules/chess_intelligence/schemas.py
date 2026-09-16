"""Pydantic contracts for canonical chess games and puzzles."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnnotatedChessMoveSchema(BaseModel):
    ply: int
    move_number: int
    side: str
    san: str
    uci: str
    fen_before: str
    fen_after: str


class ChessGameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    white_player: str | None = None
    black_player: str | None = None
    white_rating: int | None = None
    black_rating: int | None = None
    event: str | None = None
    site: str | None = None
    round: str | None = None
    game_date: str | None = None
    year: int | None = None
    result: str | None = None
    eco: str | None = None
    opening: str | None = None
    variation: str | None = None
    starting_fen: str
    final_fen: str | None = None
    normalized_pgn: str
    move_count: int
    source_provider: str | None = None
    source_external_id: str | None = None
    source_url: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str
    game_fingerprint: str
    is_famous: bool = False
    famous_title: str | None = None
    historical_tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ChessPuzzleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    external_id: str
    provider: str
    starting_fen: str
    solution_moves_uci: list[str] = Field(default_factory=list)
    solution_moves_san: list[str] = Field(default_factory=list)
    rating: int | None = None
    rating_deviation: float | None = None
    popularity: int | None = None
    play_count: int | None = None
    themes: list[str] = Field(default_factory=list)
    opening_tags: list[str] = Field(default_factory=list)
    source_game_id: str | None = None
    source_game_url: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime | None = None
    import_batch_id: str | None = None
    license_note: str | None = None
    puzzle_fingerprint: str
    content_hash: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ChessGamePageResponse(BaseModel):
    items: list[ChessGameResponse]
    next_cursor: str | None = None
    has_more: bool = False


class ChessPuzzlePageResponse(BaseModel):
    items: list[ChessPuzzleResponse]
    next_cursor: str | None = None
    has_more: bool = False


class ChessGameImportRequest(BaseModel):
    pgn: str = Field(min_length=1)
    provider: str = Field(default="manual", max_length=64)
    external_id: str | None = Field(default=None, max_length=128)
    source_url: str | None = Field(default=None, max_length=1024)
    source_name: str | None = Field(default=None, max_length=255)

    @field_validator("pgn", mode="before")
    @classmethod
    def _strip_pgn(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("provider", "external_id", "source_url", "source_name", mode="before")
    @classmethod
    def _strip_opt(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ChessGameImportResponse(BaseModel):
    game: ChessGameResponse
    created_game: bool
    created_source: bool


class ChessGameVideoRequest(BaseModel):
    """Render options for ``POST /chess/games/{id}/video`` (PGN from catalog)."""

    orientation: str = Field(default="white", pattern="^(white|black)$")
    render_preset: str = Field(
        default="economy_vertical",
        pattern="^(economy_vertical|social_vertical|square|horizontal)$",
    )
    board_theme: str = Field(
        default="classic_wood",
        pattern="^(classic_wood|tournament_green|midnight_blue|slate|high_contrast)$",
    )
    seconds_per_move: float = Field(default=1.0, ge=0.2, le=10.0)
    include_coordinates: bool = True
    include_move_text: bool = True
    title: str | None = Field(default=None, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)

    @field_validator("orientation", "render_preset", "board_theme", mode="before")
    @classmethod
    def _normalize_enums(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class ChessAnalysisRequest(BaseModel):
    """Optional overrides; unset fields use server STOCKFISH / CHESS_ENGINE_* defaults."""

    depth: int | None = Field(default=None, ge=1, le=40)
    time_limit_seconds: float | None = Field(default=None, gt=0, le=60)


class ChessPositionAnalysisSchema(BaseModel):
    """Per-ply snapshot. Scores are White POV (positive = White better)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ply: int
    fen: str
    evaluation_cp: int | None = None
    mate_in: int | None = None
    evaluation_before_cp: int | None = None
    mate_before: int | None = None
    evaluation_after_cp: int | None = None
    mate_after: int | None = None
    evaluation_delta: int | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None
    played_move_uci: str
    played_move_san: str
    depth: int = 0
    nodes: int = 0
    engine_name: str | None = None
    engine_version: str | None = None


class ChessCriticalMomentSchema(BaseModel):
    """Heuristic moment: engine facts + classification; editorial copy via narrative node."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ply: int
    classification: str
    confidence: float
    detection_method: str
    engine_facts: dict[str, Any] = Field(default_factory=dict)
    heuristic_summary: str
    editorial_description: str | None = None


class ChessTacticalPatternSchema(BaseModel):
    """Geometric/material pattern with explicit confidence + detection method."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ply: int
    pattern: str
    confidence: float
    detection_method: str
    facts: dict[str, Any] = Field(default_factory=dict)
    summary: str


class ChessContentOpportunityScoreSchema(BaseModel):
    """Transparent score: components always explain the total."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    chess_game_id: UUID
    analysis_job_id: UUID | None = None
    score: int
    components: dict[str, int] = Field(default_factory=dict)
    reasons: dict[str, list[str]] = Field(default_factory=dict)
    formula_version: str = "content_opportunity_v1"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    persisted: bool = True


class ChessAnalysisJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    chess_game_id: UUID
    status: str
    progress: float = 0.0
    error_message: str | None = None
    depth: int | None = None
    time_limit_seconds: float | None = None
    hash_mb: int = 64
    threads: int = 1
    engine_name: str | None = None
    engine_version: str | None = None
    analysis_settings: dict[str, Any] = Field(default_factory=dict)
    ply_count: int = 0
    created_at: datetime
    updated_at: datetime
    positions: list[ChessPositionAnalysisSchema] = Field(default_factory=list)
    critical_moments: list[ChessCriticalMomentSchema] = Field(default_factory=list)
    tactical_patterns: list[ChessTacticalPatternSchema] = Field(default_factory=list)
    content_opportunity: ChessContentOpportunityScoreSchema | None = None
