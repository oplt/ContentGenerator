"""Chess engine adapter contracts (Stockfish is an external binary)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import chess


@dataclass(slots=True, frozen=True)
class EngineScore:
    """Normalized evaluation from **White's perspective**.

    Convention (documented for all consumers):
    - ``cp``: centipawns; positive = White better, negative = Black better.
    - ``mate``: plies to mate; positive = White mates, negative = Black mates.
    - Exactly one of ``cp`` / ``mate`` is set (never both).
    - Do **not** subtract or compare ``cp`` against mate scores.
    """

    cp: int | None = None
    mate: int | None = None


@dataclass(slots=True, frozen=True)
class PositionEngineResult:
    fen: str
    score: EngineScore
    best_move_uci: str | None
    best_move_san: str | None
    depth: int
    nodes: int
    engine_name: str
    engine_version: str


@dataclass(slots=True, frozen=True)
class EngineLimit:
    depth: int | None = None
    time_seconds: float | None = None


class ChessEngine(Protocol):
    """Sync engine session — opened/closed by the worker, never by HTTP handlers."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def analyse(self, board: chess.Board, limit: EngineLimit) -> PositionEngineResult: ...

    def close(self) -> None: ...
