"""Orchestrate high-confidence tactical pattern detection across a game."""

from __future__ import annotations

import chess

from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.tactical_detectors import (
    TacticalPatternCandidate,
    detect_absolute_pin,
    detect_back_rank_mate,
    detect_discovered_attack,
    detect_double_attack,
    detect_fork,
    detect_piece_sacrifice,
    detect_promotion,
    detect_skewer,
    detect_smothered_mate,
)

__all__ = ["TacticalPatternCandidate", "detect_tactical_patterns"]


def detect_tactical_patterns(
    plies: list[PlyAnalysis],
    *,
    starting_fen: str,
) -> list[TacticalPatternCandidate]:
    """Walk played moves; attach high-confidence geometric patterns only."""
    out: list[TacticalPatternCandidate] = []
    board = chess.Board(starting_fen)

    for ply_row in plies:
        try:
            move = chess.Move.from_uci(ply_row.played_move_uci)
        except ValueError:
            board = chess.Board(ply_row.fen)
            continue
        if move not in board.legal_moves:
            board = chess.Board(ply_row.fen)
            continue

        before = board.copy(stack=False)
        mover = before.turn
        after = before.copy(stack=False)
        after.push(move)

        for item in (
            detect_promotion(move, ply_row.ply),
            detect_fork(after, move, ply_row.ply),
            detect_skewer(after, move, ply_row.ply),
            detect_discovered_attack(before, after, move, ply_row.ply),
            detect_double_attack(after, move, ply_row.ply),
            detect_back_rank_mate(after, ply_row.ply),
            detect_smothered_mate(after, ply_row.ply),
            detect_piece_sacrifice(before, after, move, ply_row.ply),
        ):
            if item is not None:
                out.append(item)
        out.extend(detect_absolute_pin(before, after, mover, ply_row.ply))
        board = chess.Board(ply_row.fen)

    return out
