"""Stockfish UCI adapter via python-chess (external binary, not a Python package)."""

from __future__ import annotations

from pathlib import Path

import chess
import chess.engine

from backend.modules.chess_intelligence.engine.base import (
    ChessEngine,
    EngineLimit,
    PositionEngineResult,
)
from backend.modules.chess_intelligence.engine.scores import score_from_pov


class ChessEngineConfigError(RuntimeError):
    """Stockfish path missing or not executable."""


class StockfishEngine:
    """Thin wrapper around ``chess.engine.SimpleEngine.popen_uci``."""

    def __init__(
        self,
        path: str,
        *,
        hash_mb: int = 64,
        threads: int = 1,
    ) -> None:
        resolved = Path(path).expanduser()
        if not path.strip() or not resolved.is_file():
            raise ChessEngineConfigError(
                f"STOCKFISH_PATH is unset or not a file: {path!r}"
            )
        self._engine = chess.engine.SimpleEngine.popen_uci(str(resolved))
        self._name = "Stockfish"
        self._version = "unknown"
        try:
            identity = self._engine.id
            self._name = str(identity.get("name") or "Stockfish")
            self._version = str(identity.get("name") or "unknown")
        except Exception:  # noqa: BLE001 — identity optional
            pass
        options: dict[str, int] = {}
        if hash_mb > 0:
            options["Hash"] = hash_mb
        if threads > 0:
            options["Threads"] = threads
        if options:
            try:
                self._engine.configure(options)
            except chess.engine.EngineError:
                pass

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def analyse(self, board: chess.Board, limit: EngineLimit) -> PositionEngineResult:
        chess_limit = chess.engine.Limit(
            depth=limit.depth,
            time=limit.time_seconds,
        )
        info = self._engine.analyse(board, chess_limit)
        score_raw = info.get("score")
        if score_raw is None:
            score = score_from_pov(
                chess.engine.PovScore(chess.engine.Cp(0), chess.WHITE)
            )
        else:
            score = score_from_pov(score_raw)

        best_uci: str | None = None
        best_san: str | None = None
        pv = info.get("pv") or []
        if pv:
            move = pv[0]
            best_uci = move.uci()
            try:
                best_san = board.san(move)
            except ValueError:
                best_san = best_uci

        return PositionEngineResult(
            fen=board.fen(),
            score=score,
            best_move_uci=best_uci,
            best_move_san=best_san,
            depth=int(info.get("depth") or limit.depth or 0),
            nodes=int(info.get("nodes") or 0),
            engine_name=self.name,
            engine_version=self.version,
        )

    def close(self) -> None:
        self._engine.quit()


def open_stockfish(
    path: str,
    *,
    hash_mb: int = 64,
    threads: int = 1,
) -> ChessEngine:
    return StockfishEngine(path, hash_mb=hash_mb, threads=threads)
