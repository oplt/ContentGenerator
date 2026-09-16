"""Individual high-confidence tactical detectors (geometry + material)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chess

PIECE_CP = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 10000,
}

@dataclass(slots=True, frozen=True)
class TacticalPatternCandidate:
    ply: int
    pattern: str
    confidence: float
    detection_method: str
    facts: dict[str, Any]
    summary: str

def _cand(
    ply: int,
    pattern: str,
    confidence: float,
    method: str,
    summary: str,
    facts: dict[str, Any] | None = None,
) -> TacticalPatternCandidate:
    return TacticalPatternCandidate(
        ply=ply,
        pattern=pattern,
        confidence=confidence,
        detection_method=method,
        facts=facts or {},
        summary=summary,
    )

def _valuable_or_loose(board: chess.Board, sq: chess.Square, attacker: chess.Color) -> bool:
    victim = board.piece_at(sq)
    if victim is None or victim.color == attacker:
        return False
    if victim.piece_type == chess.KING:
        return True
    defended = board.is_attacked_by(not attacker, sq)
    return victim.piece_type in (chess.QUEEN, chess.ROOK) or not defended

def detect_fork(board: chess.Board, move: chess.Move, ply: int) -> TacticalPatternCandidate | None:
    piece = board.piece_at(move.to_square)
    if piece is None:
        return None
    targets = [
        chess.square_name(sq)
        for sq in board.attacks(move.to_square)
        if _valuable_or_loose(board, sq, piece.color)
    ]
    if len(targets) < 2:
        return None
    return _cand(
        ply,
        "fork",
        0.85,
        "multi_valuable_attack",
        f"Ply {ply}: piece forks {len(targets)} valuable/loose targets.",
        {"uci": move.uci(), "targets": targets},
    )

def detect_absolute_pin(
    before: chess.Board, after: chess.Board, mover: chess.Color, ply: int
) -> list[TacticalPatternCandidate]:
    out: list[TacticalPatternCandidate] = []
    enemy = not mover
    for sq in chess.SQUARES:
        piece = after.piece_at(sq)
        if piece is None or piece.color != enemy or piece.piece_type == chess.KING:
            continue
        if after.is_pinned(enemy, sq) and not before.is_pinned(enemy, sq):
            out.append(
                _cand(
                    ply,
                    "pin",
                    0.9,
                    "absolute_pin_appears",
                    f"Ply {ply}: absolute pin on {chess.square_name(sq)}.",
                    {"square": chess.square_name(sq), "piece": piece.symbol()},
                )
            )
    return out

def _ray_behind(
    board: chess.Board, slider: chess.Square, through: chess.Square
) -> chess.Square | None:
    file_s, rank_s = chess.square_file(slider), chess.square_rank(slider)
    file_t, rank_t = chess.square_file(through), chess.square_rank(through)
    df, dr = file_t - file_s, rank_t - rank_s
    if df == 0 and dr == 0:
        return None
    step_f = 0 if df == 0 else (1 if df > 0 else -1)
    step_r = 0 if dr == 0 else (1 if dr > 0 else -1)
    if df != 0 and dr != 0 and abs(df) != abs(dr):
        return None
    f, r = file_s + step_f, rank_s + step_r
    seen = False
    while 0 <= f <= 7 and 0 <= r <= 7:
        sq = chess.square(f, r)
        if sq == through:
            seen = True
        elif seen and board.piece_at(sq) is not None:
            return sq
        elif not seen and board.piece_at(sq) is not None:
            return None
        f += step_f
        r += step_r
    return None

def detect_skewer(board: chess.Board, move: chess.Move, ply: int) -> TacticalPatternCandidate | None:
    piece = board.piece_at(move.to_square)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return None
    for mid in board.attacks(move.to_square):
        front = board.piece_at(mid)
        if front is None or front.color == piece.color or front.piece_type == chess.KING:
            continue
        behind_sq = _ray_behind(board, move.to_square, mid)
        if behind_sq is None:
            continue
        behind = board.piece_at(behind_sq)
        if behind is None or behind.color == piece.color:
            continue
        if PIECE_CP[front.piece_type] > PIECE_CP[behind.piece_type]:
            return _cand(
                ply,
                "skewer",
                0.8,
                "ray_higher_then_lower",
                f"Ply {ply}: skewer {chess.square_name(mid)} → {chess.square_name(behind_sq)}.",
                {"front": chess.square_name(mid), "behind": chess.square_name(behind_sq)},
            )
    return None

def detect_discovered_attack(
    before: chess.Board, after: chess.Board, move: chess.Move, ply: int
) -> TacticalPatternCandidate | None:
    mover = before.turn
    enemy = not mover
    for sq in chess.SQUARES:
        piece = after.piece_at(sq)
        if piece is None or piece.color != mover or sq == move.to_square:
            continue
        if before.piece_at(sq) is None:
            continue
        for target in after.attacks(sq):
            victim = after.piece_at(target)
            if victim is None or victim.color != enemy:
                continue
            if victim.piece_type not in (chess.KING, chess.QUEEN, chess.ROOK):
                continue
            if target not in before.attacks(sq):
                return _cand(
                    ply,
                    "discovered_attack",
                    0.8,
                    "uncovered_slider_or_piece",
                    f"Ply {ply}: discovered attack on {chess.square_name(target)}.",
                    {
                        "attacker": chess.square_name(sq),
                        "target": chess.square_name(target),
                        "moved": move.uci(),
                    },
                )
    return None

def detect_double_attack(
    board: chess.Board, move: chess.Move, ply: int
) -> TacticalPatternCandidate | None:
    if not board.is_check():
        return None
    piece = board.piece_at(move.to_square)
    if piece is None:
        return None
    extra = [
        chess.square_name(sq)
        for sq in board.attacks(move.to_square)
        if _valuable_or_loose(board, sq, piece.color)
        and board.piece_at(sq) is not None
        and board.piece_at(sq).piece_type != chess.KING  # type: ignore[union-attr]
    ]
    if not extra:
        return None
    return _cand(
        ply,
        "double_attack",
        0.75,
        "check_plus_second_threat",
        f"Ply {ply}: check with additional threat(s).",
        {"extra_targets": extra},
    )

def detect_back_rank_mate(board: chess.Board, ply: int) -> TacticalPatternCandidate | None:
    if not board.is_checkmate():
        return None
    king_sq = board.king(board.turn)
    if king_sq is None or chess.square_rank(king_sq) not in (0, 7):
        return None
    rank = chess.square_rank(king_sq)
    for sq in board.checkers():
        piece = board.piece_at(sq)
        if piece and piece.piece_type in (chess.ROOK, chess.QUEEN) and chess.square_rank(sq) == rank:
            return _cand(
                ply,
                "back_rank_mate",
                0.95,
                "mate_back_rank_slider",
                f"Ply {ply}: back-rank mate.",
                {"king": chess.square_name(king_sq), "checker": chess.square_name(sq)},
            )
    return None

def detect_smothered_mate(board: chess.Board, ply: int) -> TacticalPatternCandidate | None:
    if not board.is_checkmate():
        return None
    loser = board.turn
    king_sq = board.king(loser)
    checkers = list(board.checkers())
    if king_sq is None or len(checkers) != 1:
        return None
    checker = board.piece_at(checkers[0])
    if checker is None or checker.piece_type != chess.KNIGHT:
        return None
    for sq in board.attacks(king_sq):
        occ = board.piece_at(sq)
        if occ is None or occ.color != loser:
            return None
    return _cand(
        ply,
        "smothered_mate",
        0.95,
        "knight_mate_smothered_king",
        f"Ply {ply}: smothered mate.",
        {"king": chess.square_name(king_sq)},
    )

def detect_promotion(move: chess.Move, ply: int) -> TacticalPatternCandidate | None:
    if move.promotion is None:
        return None
    under = move.promotion != chess.QUEEN
    name = "underpromotion" if under else "promotion"
    return _cand(
        ply,
        name,
        1.0,
        "move_promotion_flag",
        f"Ply {ply}: {name} to {chess.piece_name(move.promotion)}.",
        {"promotion": chess.piece_symbol(move.promotion)},
    )

def _side_material(board: chess.Board, color: chess.Color) -> int:
    total = 0
    for pt, val in PIECE_CP.items():
        if pt == chess.KING:
            continue
        total += len(board.pieces(pt, color)) * val
    return total

def detect_piece_sacrifice(
    before: chess.Board, after: chess.Board, move: chess.Move, ply: int
) -> TacticalPatternCandidate | None:
    mover = before.turn
    rel_before = _side_material(before, mover) - _side_material(before, not mover)
    rel_after = _side_material(after, mover) - _side_material(after, not mover)
    net_loss = rel_before - rel_after
    if net_loss < 300:
        return None
    for pt, name in (
        (chess.QUEEN, "queen_sacrifice"),
        (chess.ROOK, "rook_sacrifice"),
        (chess.BISHOP, "bishop_sacrifice"),
        (chess.KNIGHT, "knight_sacrifice"),
    ):
        if len(after.pieces(pt, mover)) < len(before.pieces(pt, mover)):
            if pt == chess.ROOK and 150 <= net_loss <= 350:
                return _cand(
                    ply,
                    "exchange_sacrifice",
                    0.7,
                    "rook_for_minor_material",
                    f"Ply {ply}: exchange sacrifice (~{net_loss}cp).",
                    {"material_loss_cp": net_loss, "uci": move.uci()},
                )
            return _cand(
                ply,
                name,
                0.75,
                "named_piece_material_drop",
                f"Ply {ply}: {name.replace('_', ' ')} (~{net_loss}cp).",
                {"material_loss_cp": net_loss, "uci": move.uci()},
            )
    return None
