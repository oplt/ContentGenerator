"""Typed provider DTOs — adapters map HTTP JSON here; never leak raw payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChessGameSearchQuery(BaseModel):
    """Provider-agnostic historical game search."""

    moves: str | None = Field(
        default=None,
        description="Move sequence (UCI tokens or SAN), provider-interpreted",
    )
    fen: str | None = None
    year_from: int | None = Field(default=None, ge=1400, le=2100)
    year_to: int | None = Field(default=None, ge=1400, le=2100)
    max_games: int = Field(default=15, ge=1, le=100)
    player: str | None = None
    white: str | None = None
    black: str | None = None

    @field_validator("moves", "fen", "player", "white", "black", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ExternalChessGameSummary(BaseModel):
    """Lightweight search hit — no full PGN required."""

    provider: str
    external_id: str
    white_player: str | None = None
    black_player: str | None = None
    white_rating: int | None = None
    black_rating: int | None = None
    year: int | None = None
    game_date: str | None = None
    event: str | None = None
    result: str | None = None
    eco: str | None = None
    source_url: str | None = None


class ExternalChessGame(BaseModel):
    """Full external game ready for normalization into ChessGame."""

    provider: str
    external_id: str
    pgn: str = Field(min_length=1)

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
    source_url: str | None = None
    # Curated key/values only — provider adapter chooses what to keep.
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pgn", mode="before")
    @classmethod
    def _strip_pgn(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ExternalChessPuzzle(BaseModel):
    """Full external puzzle ready for normalization into ChessPuzzle."""

    provider: str
    external_id: str
    starting_fen: str = Field(min_length=1)
    solution_moves_uci: list[str] = Field(min_length=1)

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

    @field_validator("starting_fen", mode="before")
    @classmethod
    def _strip_fen(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("solution_moves_uci", mode="before")
    @classmethod
    def _normalize_uci(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [str(m).strip().lower() for m in value if str(m).strip()]
