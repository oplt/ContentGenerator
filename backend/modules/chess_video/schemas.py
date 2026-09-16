from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.chess_video.parser import MAX_INPUT_BYTES

# Align with parser byte cap (ASCII PGN ≈ same char count; parser still enforces UTF-8 bytes).
_MAX_SOURCE_CHARS = MAX_INPUT_BYTES

_PRESET_PATTERN = (
    "^(economy_vertical|social_vertical|square|horizontal)$"
)
_FORMAT_PATTERN = "^(pgn|san|uci|auto)$"
_BOARD_THEME_PATTERN = (
    "^(classic_wood|tournament_green|midnight_blue|slate|high_contrast)$"
)


class ChessVideoJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    created_by_user_id: UUID | None = None

    status: str
    stage: str
    progress: float

    input_format: str
    source_hash: str | None = None
    chess_game_id: UUID | None = None

    white_player: str | None = None
    black_player: str | None = None
    event: str | None = None
    game_date: str | None = None
    result: str | None = None

    starting_fen: str | None = None
    move_count: int = 0

    orientation: str
    render_preset: str
    board_theme: str = "classic_wood"
    seconds_per_move: float
    include_coordinates: bool
    include_move_text: bool

    title: str | None = None
    subtitle: str | None = None

    renderer_version: str | None = None
    render_fingerprint: str | None = None

    video_public_url: str | None = None
    thumbnail_public_url: str | None = None

    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None

    error_message: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChessVideoCreateRequest(BaseModel):
    """Create a render job from raw moves **or** a catalog ``chess_game_id``."""

    source_text: str | None = Field(default=None, max_length=_MAX_SOURCE_CHARS)
    chess_game_id: UUID | None = None
    input_format: str = Field(default="auto", pattern=_FORMAT_PATTERN)
    orientation: str = Field(default="white", pattern="^(white|black)$")
    render_preset: str = Field(default="economy_vertical", pattern=_PRESET_PATTERN)
    board_theme: str = Field(default="classic_wood", pattern=_BOARD_THEME_PATTERN)
    seconds_per_move: float = Field(default=1.0, ge=0.2, le=10.0)
    include_coordinates: bool = True
    include_move_text: bool = True
    title: str | None = Field(default=None, max_length=255)
    subtitle: str | None = Field(default=None, max_length=255)

    @field_validator("source_text", mode="before")
    @classmethod
    def _strip_source(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("input_format", "orientation", "render_preset", "board_theme", mode="before")
    @classmethod
    def _normalize_enums(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _require_source_or_catalog_game(self) -> ChessVideoCreateRequest:
        if self.chess_game_id is None and not self.source_text:
            raise ValueError("Provide source_text or chess_game_id")
        return self


class ChessVideoValidateRequest(BaseModel):
    source_text: str = Field(min_length=1, max_length=_MAX_SOURCE_CHARS)
    input_format: str = Field(default="auto", pattern=_FORMAT_PATTERN)

    @field_validator("source_text", mode="before")
    @classmethod
    def _strip_source(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("input_format", mode="before")
    @classmethod
    def _normalize_format(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class ChessVideoValidateResponse(BaseModel):
    valid: bool
    input_format: str
    detected_format: str | None = None
    normalized_pgn: str | None = None
    white_player: str | None = None
    black_player: str | None = None
    event: str | None = None
    game_date: str | None = None
    result: str | None = None
    starting_fen: str | None = None
    move_count: int = 0
    errors: list[str] = Field(default_factory=list)
