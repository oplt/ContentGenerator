"""Score helpers — White POV; refuse careless cp↔mate arithmetic."""

from __future__ import annotations

import chess.engine

from backend.modules.chess_intelligence.engine.base import EngineScore


def score_from_pov(info_score: chess.engine.PovScore) -> EngineScore:
    """Convert python-chess score to White-perspective EngineScore."""
    white = info_score.white()
    if white.is_mate():
        mate = white.mate()
        assert mate is not None
        return EngineScore(mate=int(mate))
    cp = white.score(mate_score=None)
    if cp is None:
        return EngineScore(cp=0)
    return EngineScore(cp=int(cp))


def score_delta(before: EngineScore, after: EngineScore) -> int | None:
    """Centipawn delta (after − before) when both sides are non-mate; else None."""
    if before.mate is not None or after.mate is not None:
        return None
    if before.cp is None or after.cp is None:
        return None
    return after.cp - before.cp


def format_score(score: EngineScore) -> str:
    if score.mate is not None:
        sign = "+" if score.mate > 0 else ""
        return f"M{sign}{score.mate}"
    cp = score.cp or 0
    return f"{cp / 100:+.2f}"
