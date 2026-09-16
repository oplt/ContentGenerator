"""Deterministic critical-moment heuristics from engine ply analysis.

Layers (kept separate — no LLM labels):
  engine_facts        — raw eval/mate/move fields from Stockfish analysis
  classification      — heuristic tag (blunder, mate_appears, …)
  heuristic_summary   — short template sentence (not editorial copy)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chess

from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis

# Centipawn thresholds (White POV → converted to mover loss).
BLUNDER_CP = 200
MISTAKE_CP = 100
SWING_CP = 150
MISSED_WIN_BEFORE_CP = 200
SACRIFICE_MATERIAL_CP = 200  # ≈2 pawns of material
SACRIFICE_EVAL_CEILING = 50  # mover eval loss after sacrifice must stay below this
OPENING_END_PLY = 20
ENDGAME_PIECE_MAX = 10  # non-king/pawn pieces on board


@dataclass(slots=True, frozen=True)
class CriticalMomentCandidate:
    ply: int
    classification: str
    confidence: float
    detection_method: str
    engine_facts: dict[str, Any]
    heuristic_summary: str


def _white_moved(ply: int) -> bool:
    return ply % 2 == 1


def _centipawn_loss_for_mover(ply: int, delta: int | None) -> int | None:
    if delta is None:
        return None
    # White POV delta: White worse ⇒ negative; Black worse ⇒ positive.
    return max(0, -delta if _white_moved(ply) else delta)


def _material_cp(board: chess.Board) -> int:
    values = {
        chess.PAWN: 100,
        chess.KNIGHT: 300,
        chess.BISHOP: 300,
        chess.ROOK: 500,
        chess.QUEEN: 900,
    }
    total = 0
    for piece_type, value in values.items():
        total += len(board.pieces(piece_type, chess.WHITE)) * value
        total -= len(board.pieces(piece_type, chess.BLACK)) * value
    return total


def _non_king_pawn_count(board: chess.Board) -> int:
    count = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        count += len(board.pieces(piece_type, chess.WHITE))
        count += len(board.pieces(piece_type, chess.BLACK))
    return count


def _facts(ply: PlyAnalysis, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "evaluation_delta": ply.evaluation_delta,
        "evaluation_before_cp": ply.evaluation_before_cp,
        "evaluation_after_cp": ply.evaluation_after_cp,
        "mate_before": ply.mate_before,
        "mate_after": ply.mate_after,
        "best_move_uci": ply.best_move_uci,
        "best_move_san": ply.best_move_san,
        "played_move_uci": ply.played_move_uci,
        "played_move_san": ply.played_move_san,
        "centipawn_loss_mover": _centipawn_loss_for_mover(ply.ply, ply.evaluation_delta),
    }
    if extra:
        base.update(extra)
    return base


def _emit(
    out: list[CriticalMomentCandidate],
    ply: PlyAnalysis,
    *,
    classification: str,
    confidence: float,
    method: str,
    summary: str,
    extra: dict[str, Any] | None = None,
) -> None:
    out.append(
        CriticalMomentCandidate(
            ply=ply.ply,
            classification=classification,
            confidence=confidence,
            detection_method=method,
            engine_facts=_facts(ply, extra=extra),
            heuristic_summary=summary,
        )
    )


def detect_critical_moments(
    plies: list[PlyAnalysis],
    *,
    starting_fen: str,
) -> list[CriticalMomentCandidate]:
    """Return heuristic candidates; does not invent brilliance or LLM prose."""
    out: list[CriticalMomentCandidate] = []
    prev_fen = starting_fen
    prev_piece_count: int | None = None

    for ply in plies:
        before = chess.Board(prev_fen)
        after = chess.Board(ply.fen)
        white_moved = _white_moved(ply.ply)
        loss = _centipawn_loss_for_mover(ply.ply, ply.evaluation_delta)
        best_differs = bool(
            ply.best_move_uci and ply.best_move_uci != ply.played_move_uci
        )

        if loss is not None and loss >= BLUNDER_CP and best_differs:
            _emit(
                out,
                ply,
                classification="blunder",
                confidence=0.9,
                method="centipawn_loss_threshold",
                summary=f"Ply {ply.ply}: mover lost ≥{BLUNDER_CP}cp vs best move.",
            )
        elif loss is not None and loss >= MISTAKE_CP and best_differs:
            _emit(
                out,
                ply,
                classification="mistake",
                confidence=0.8,
                method="centipawn_loss_threshold",
                summary=f"Ply {ply.ply}: mover lost ≥{MISTAKE_CP}cp vs best move.",
            )

        if ply.evaluation_delta is not None and abs(ply.evaluation_delta) >= SWING_CP:
            _emit(
                out,
                ply,
                classification="large_evaluation_swing",
                confidence=0.85,
                method="abs_eval_delta_threshold",
                summary=f"Ply {ply.ply}: |Δeval| ≥ {SWING_CP}cp (White POV).",
            )

        before_cp = ply.evaluation_before_cp
        after_cp = ply.evaluation_after_cp
        if (
            before_cp is not None
            and after_cp is not None
            and before_cp * after_cp < 0
            and abs(before_cp) >= 50
            and abs(after_cp) >= 50
        ):
            _emit(
                out,
                ply,
                classification="turning_point",
                confidence=0.75,
                method="eval_sign_flip",
                summary=f"Ply {ply.ply}: evaluation sign flipped (White POV).",
            )

        if ply.mate_before is None and ply.mate_after is not None:
            _emit(
                out,
                ply,
                classification="forced_mate",
                confidence=0.95,
                method="mate_appears",
                summary=f"Ply {ply.ply}: mate score appeared (M{ply.mate_after}).",
            )
        if ply.mate_before is not None and ply.mate_after is None:
            _emit(
                out,
                ply,
                classification="mate_threat",
                confidence=0.9,
                method="mate_disappears",
                summary=f"Ply {ply.ply}: prior mate score (M{ply.mate_before}) cleared.",
            )

        # Missed win: strong advantage / mate available, played non-best, large loss.
        mover_winning_before = False
        if ply.mate_before is not None:
            mover_winning_before = (ply.mate_before > 0) if white_moved else (ply.mate_before < 0)
        elif before_cp is not None:
            mover_winning_before = (
                before_cp >= MISSED_WIN_BEFORE_CP
                if white_moved
                else before_cp <= -MISSED_WIN_BEFORE_CP
            )
        if mover_winning_before and best_differs and loss is not None and loss >= MISTAKE_CP:
            _emit(
                out,
                ply,
                classification="missed_win",
                confidence=0.85,
                method="advantage_then_deviation",
                summary=f"Ply {ply.ply}: winning/mate chance and large deviation from best.",
            )

        # Sacrifice: mover gives material (≥2 pawns) but eval loss stays small / improves.
        mat_before = _material_cp(before)
        mat_after = _material_cp(after)
        mat_delta_white = mat_after - mat_before
        mover_material_loss = -mat_delta_white if white_moved else mat_delta_white
        if mover_material_loss >= SACRIFICE_MATERIAL_CP and (
            loss is None or loss <= SACRIFICE_EVAL_CEILING
        ):
            _emit(
                out,
                ply,
                classification="sacrifice",
                confidence=0.7,
                method="material_drop_with_eval_hold",
                summary=f"Ply {ply.ply}: ≥{SACRIFICE_MATERIAL_CP}cp material given with limited eval loss.",
                extra={
                    "material_delta_white_cp": mat_delta_white,
                    "mover_material_loss_cp": mover_material_loss,
                },
            )

        piece_count = _non_king_pawn_count(after)
        if ply.ply == OPENING_END_PLY:
            _emit(
                out,
                ply,
                classification="opening_transition",
                confidence=0.55,
                method="ply_boundary",
                summary=f"Ply {ply.ply}: conventional opening→middlegame boundary.",
            )
        if prev_piece_count is not None and prev_piece_count > ENDGAME_PIECE_MAX and piece_count <= ENDGAME_PIECE_MAX:
            _emit(
                out,
                ply,
                classification="endgame_transition",
                confidence=0.7,
                method="piece_count_threshold",
                summary=f"Ply {ply.ply}: major/minor pieces ≤ {ENDGAME_PIECE_MAX}.",
                extra={"piece_count": piece_count},
            )

        prev_fen = ply.fen
        prev_piece_count = piece_count

    return out
