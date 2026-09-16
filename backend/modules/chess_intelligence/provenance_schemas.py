"""Provenance / source-evidence response contracts (Phase 19)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChessSourceRecordSchema(BaseModel):
    """One provider sighting — never replaced by LLM/editorial copy."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID | None = None
    provider: str
    external_id: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_batch_id: str | None = None
    license_note: str | None = None
    retrieved_at: datetime | None = None
    is_primary: bool = False


class ChessGameProvenanceResponse(BaseModel):
    entity_type: Literal["chess_game"] = "chess_game"
    chess_game_id: UUID
    # Authoritative move evidence (catalog PGN) — not narrative.
    normalized_pgn: str
    content_hash: str
    game_fingerprint: str
    primary_source: ChessSourceRecordSchema | None = None
    sources: list[ChessSourceRecordSchema] = Field(default_factory=list)
    evidence_note: str = (
        "Source evidence (PGN + provider records) is authoritative; "
        "editorial/LLM narrative must not replace it."
    )


class ChessPuzzleProvenanceResponse(BaseModel):
    entity_type: Literal["chess_puzzle"] = "chess_puzzle"
    chess_puzzle_id: UUID
    provider: str
    external_id: str
    starting_fen: str
    solution_moves_uci: list[str] = Field(default_factory=list)
    source_game_id: str | None = None
    source_game_url: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_batch_id: str | None = None
    license_note: str | None = None
    retrieved_at: datetime | None = None
    content_hash: str
    puzzle_fingerprint: str
    evidence_note: str = (
        "Puzzle FEN/solution and provider ids are authoritative; "
        "explanations must not replace source evidence."
    )


class ChessVideoProvenanceResponse(BaseModel):
    """Trace: video job → optional catalog game → provider sources → PGN."""

    entity_type: Literal["chess_video"] = "chess_video"
    chess_video_job_id: UUID
    chess_game_id: UUID | None = None
    normalized_pgn: str | None = None
    source_hash: str | None = None
    game: ChessGameProvenanceResponse | None = None
    evidence_note: str = (
        "Rendered video derives from stored PGN/source_text; "
        "when chess_game_id is set, catalog provenance is authoritative."
    )
