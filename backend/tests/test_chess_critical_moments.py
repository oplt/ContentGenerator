"""Phase 15 — deterministic critical-moment heuristics."""

from __future__ import annotations

from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.critical_moments import (
    BLUNDER_CP,
    detect_critical_moments,
)

_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _ply(
    *,
    ply: int,
    fen: str,
    delta: int | None,
    before_cp: int | None,
    after_cp: int | None,
    mate_before: int | None = None,
    mate_after: int | None = None,
    best: str = "e2e4",
    played: str = "a2a3",
) -> PlyAnalysis:
    return PlyAnalysis(
        ply=ply,
        fen=fen,
        evaluation_cp=after_cp,
        mate_in=mate_after,
        evaluation_before_cp=before_cp,
        mate_before=mate_before,
        evaluation_after_cp=after_cp,
        mate_after=mate_after,
        evaluation_delta=delta,
        best_move_uci=best,
        best_move_san="e4",
        played_move_uci=played,
        played_move_san="a3",
        depth=8,
        nodes=100,
        engine_name="Fake",
        engine_version="0",
    )


def test_blunder_and_swing_detection() -> None:
    # After 1.e4
    fen_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    plies = [
        _ply(
            ply=1,
            fen=fen_e4,
            delta=-BLUNDER_CP - 20,
            before_cp=30,
            after_cp=-190,
            best="e2e4",
            played="a2a4",
        )
    ]
    moments = detect_critical_moments(plies, starting_fen=_START)
    labels = {m.classification for m in moments}
    assert "blunder" in labels
    assert "large_evaluation_swing" in labels
    blunder = next(m for m in moments if m.classification == "blunder")
    assert blunder.engine_facts["centipawn_loss_mover"] >= BLUNDER_CP
    assert blunder.heuristic_summary
    assert blunder.detection_method == "centipawn_loss_threshold"


def test_mate_appears_and_turning_point() -> None:
    fen = "6k1/5ppp/8/8/8/8/5PPP/4Q1K1 w - - 0 1"
    after = "6k1/5ppp/8/8/8/8/5PPP/4QK2 b - - 1 1"
    plies = [
        _ply(
            ply=1,
            fen=after,
            delta=None,
            before_cp=100,
            after_cp=None,
            mate_before=None,
            mate_after=2,
            best="e1f1",
            played="e1f1",
        ),
        _ply(
            ply=2,
            fen=fen,
            delta=-250,
            before_cp=120,
            after_cp=-130,
            best="g8h8",
            played="g7g5",
        ),
    ]
    moments = detect_critical_moments(plies, starting_fen=fen)
    labels = {m.classification for m in moments}
    assert "forced_mate" in labels
    assert "turning_point" in labels


def test_sacrifice_material_hold() -> None:
    # White gives queen for nothing on paper but eval holds (contrived FENs).
    before = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    # Remove white queen from a1-ish setup: use position without white queen
    after = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1"
    plies = [
        _ply(
            ply=1,
            fen=after,
            delta=-30,
            before_cp=20,
            after_cp=-10,
            best="d1d2",
            played="d1d2",
        )
    ]
    moments = detect_critical_moments(plies, starting_fen=before)
    assert any(m.classification == "sacrifice" for m in moments)


def test_no_brilliant_label() -> None:
    fen_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    plies = [
        _ply(ply=1, fen=fen_e4, delta=15, before_cp=0, after_cp=15, best="e2e4", played="e2e4")
    ]
    moments = detect_critical_moments(plies, starting_fen=_START)
    assert all(m.classification != "brilliant" for m in moments)
