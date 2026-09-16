"""Phase 16 — high-confidence tactical pattern detectors."""

from __future__ import annotations

import chess

from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.tactical_detectors import (
    detect_back_rank_mate,
    detect_fork,
    detect_promotion,
    detect_smothered_mate,
)
from backend.modules.chess_intelligence.engine.tactical_patterns import detect_tactical_patterns


def _ply(ply: int, fen: str, uci: str, san: str = "x") -> PlyAnalysis:
    return PlyAnalysis(
        ply=ply,
        fen=fen,
        evaluation_cp=0,
        mate_in=None,
        evaluation_before_cp=0,
        mate_before=None,
        evaluation_after_cp=0,
        mate_after=None,
        evaluation_delta=0,
        best_move_uci=uci,
        best_move_san=san,
        played_move_uci=uci,
        played_move_san=san,
        depth=1,
        nodes=1,
        engine_name="n/a",
        engine_version="0",
    )


def test_knight_fork_detection() -> None:
    # Knight on c7 attacks king e8 and rook a8.
    after = chess.Board("r3k3/2N5/8/8/8/8/8/4K3 b - - 1 1")
    hit = detect_fork(after, chess.Move.from_uci("b5c7"), 5)
    assert hit is not None
    assert hit.pattern == "fork"
    assert hit.confidence >= 0.8
    assert hit.detection_method == "multi_valuable_attack"


def test_promotion_and_underpromotion() -> None:
    promo = detect_promotion(chess.Move.from_uci("e7e8q"), 10)
    assert promo is not None and promo.pattern == "promotion" and promo.confidence == 1.0
    under = detect_promotion(chess.Move.from_uci("e7e8n"), 11)
    assert under is not None and under.pattern == "underpromotion"


def test_back_rank_mate() -> None:
    board = chess.Board("3R2k1/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    assert board.is_checkmate()
    hit = detect_back_rank_mate(board, 20)
    assert hit is not None
    assert hit.pattern == "back_rank_mate"


def test_smothered_mate() -> None:
    board = chess.Board("6rk/5Npp/8/8/8/8/8/4K3 b - - 0 1")
    assert board.is_checkmate()
    hit = detect_smothered_mate(board, 30)
    assert hit is not None
    assert hit.pattern == "smothered_mate"


def test_walk_detects_promotion_in_game() -> None:
    start = "8/4P3/8/8/8/8/8/4K2k w - - 0 1"
    after = chess.Board(start)
    after.push(chess.Move.from_uci("e7e8q"))
    plies = [_ply(1, after.fen(), "e7e8q", "e8=Q")]
    patterns = detect_tactical_patterns(plies, starting_fen=start)
    assert any(p.pattern == "promotion" for p in patterns)
    assert all(hasattr(p, "detection_method") and p.confidence > 0 for p in patterns)
