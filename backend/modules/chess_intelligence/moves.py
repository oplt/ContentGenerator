"""Derive annotated plies from a parsed game without persisting move rows.

Option A (chosen): store canonical PGN on ChessGame; derive moves via python-chess.
See docs/chess-intelligence-phase1.md for trade-off vs JSONB / move table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import chess

from backend.modules.chess_video.parser import ParsedChessGame

Side = Literal["white", "black"]


@dataclass(slots=True, frozen=True)
class AnnotatedChessMove:
    ply: int
    move_number: int
    side: Side
    san: str
    uci: str
    fen_before: str
    fen_after: str


def annotate_moves(game: ParsedChessGame) -> list[AnnotatedChessMove]:
    """Walk mainline and emit ply / side / SAN / UCI / FEN before+after."""
    board = chess.Board(game.starting_fen)
    out: list[AnnotatedChessMove] = []
    for ply_index, move in enumerate(game.moves):
        fen_before = board.fen()
        side: Side = "white" if board.turn == chess.WHITE else "black"
        san = game.san_moves[ply_index] if ply_index < len(game.san_moves) else board.san(move)
        uci = game.uci_moves[ply_index] if ply_index < len(game.uci_moves) else move.uci()
        board.push(move)
        ply = ply_index + 1
        out.append(
            AnnotatedChessMove(
                ply=ply,
                move_number=(ply + 1) // 2,
                side=side,
                san=san,
                uci=uci,
                fen_before=fen_before,
                fen_after=board.fen(),
            )
        )
    return out
