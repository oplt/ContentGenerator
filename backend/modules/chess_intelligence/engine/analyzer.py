"""Walk a game and produce per-ply engine analysis (sync; Celery-only)."""

from __future__ import annotations

from dataclasses import dataclass

import chess

from backend.modules.chess_intelligence.engine.base import ChessEngine, EngineLimit, EngineScore
from backend.modules.chess_intelligence.engine.scores import score_delta
from backend.modules.chess_video.parser import ParsedChessGame


@dataclass(slots=True, frozen=True)
class PlyAnalysis:
    ply: int
    fen: str
    evaluation_cp: int | None
    mate_in: int | None
    evaluation_before_cp: int | None
    mate_before: int | None
    evaluation_after_cp: int | None
    mate_after: int | None
    evaluation_delta: int | None
    best_move_uci: str | None
    best_move_san: str | None
    played_move_uci: str
    played_move_san: str
    depth: int
    nodes: int
    engine_name: str
    engine_version: str


def _pack(score: EngineScore) -> tuple[int | None, int | None]:
    return score.cp, score.mate


def analyze_game(
    parsed: ParsedChessGame,
    engine: ChessEngine,
    *,
    depth: int | None,
    time_seconds: float | None,
) -> list[PlyAnalysis]:
    """Analyse each ply: eval before (best move) and after (played move).

    Scores use White's perspective (see ``EngineScore``).
    """
    limit = EngineLimit(depth=depth, time_seconds=time_seconds)
    board = chess.Board(parsed.starting_fen)
    before = engine.analyse(board, limit)
    out: list[PlyAnalysis] = []

    for ply_index, move in enumerate(parsed.moves):
        played_uci = (
            parsed.uci_moves[ply_index]
            if ply_index < len(parsed.uci_moves)
            else move.uci()
        )
        played_san = (
            parsed.san_moves[ply_index]
            if ply_index < len(parsed.san_moves)
            else board.san(move)
        )
        board.push(move)
        after = engine.analyse(board, limit)
        before_cp, before_mate = _pack(before.score)
        after_cp, after_mate = _pack(after.score)
        out.append(
            PlyAnalysis(
                ply=ply_index + 1,
                fen=after.fen,
                evaluation_cp=after_cp,
                mate_in=after_mate,
                evaluation_before_cp=before_cp,
                mate_before=before_mate,
                evaluation_after_cp=after_cp,
                mate_after=after_mate,
                evaluation_delta=score_delta(before.score, after.score),
                best_move_uci=before.best_move_uci,
                best_move_san=before.best_move_san,
                played_move_uci=played_uci,
                played_move_san=played_san,
                depth=after.depth,
                nodes=before.nodes + after.nodes,
                engine_name=after.engine_name,
                engine_version=after.engine_version,
            )
        )
        before = after

    return out
