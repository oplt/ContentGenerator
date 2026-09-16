"""Lichess puzzle provider — daily + by-id.

Official API (lichess-org/api OpenAPI, security public):
  GET https://lichess.org/api/puzzle/daily
  GET https://lichess.org/api/puzzle/{id}

Response schema ``PuzzleAndGame`` includes ``puzzle.fen`` + ``puzzle.solution``.
Solution is validated later via ``normalize_external_puzzle`` (python-chess).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import chess

from backend.core.config import settings
from backend.modules.chess_intelligence.providers.base import (
    ChessProviderError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
)
from backend.modules.chess_intelligence.providers.dtos import ExternalChessPuzzle
from backend.modules.chess_intelligence.providers.lichess_http import (
    ProviderHealthState,
    _OutboundRateLimiter,
    lichess_request,
    site_url,
)
from backend.modules.chess_intelligence.providers.provider_cache import (
    cached_model,
    daily_puzzle_ttl_seconds,
    key_daily_puzzle,
    key_puzzle,
    policy_puzzle,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "lichess_puzzles"


def _derive_fen_from_game(*, game_pgn: str, initial_ply: int) -> str:
    """Replay SAN/UCI tokens from game.pgn up to initialPly when fen missing."""
    board = chess.Board()
    tokens = [t for t in game_pgn.replace("\n", " ").split() if t]
    ply = 0
    for token in tokens:
        if token in {"1-0", "0-1", "1/2-1/2", "*"}:
            continue
        if ply >= initial_ply:
            break
        try:
            move = board.parse_san(token)
        except ValueError:
            try:
                move = chess.Move.from_uci(token.lower())
            except ValueError as exc:
                raise ChessProviderInvalidResponseError(
                    f"Cannot replay game token '{token}' for puzzle FEN",
                    provider=PROVIDER_NAME,
                ) from exc
        if move not in board.legal_moves:
            raise ChessProviderInvalidResponseError(
                f"Illegal game move '{token}' while deriving puzzle FEN",
                provider=PROVIDER_NAME,
            )
        board.push(move)
        ply += 1
    return board.fen()


def map_puzzle_and_game(payload: dict[str, Any]) -> ExternalChessPuzzle:
    """Map Lichess PuzzleAndGame JSON → ExternalChessPuzzle (curated fields only)."""
    puzzle = payload.get("puzzle")
    game_raw = payload.get("game")
    game: dict[str, Any] = game_raw if isinstance(game_raw, dict) else {}
    if not isinstance(puzzle, dict):
        raise ChessProviderInvalidResponseError(
            "Lichess puzzle payload missing puzzle object",
            provider=PROVIDER_NAME,
        )
    puzzle_id = str(puzzle.get("id") or "").strip()
    if not puzzle_id:
        raise ChessProviderInvalidResponseError(
            "Lichess puzzle missing id", provider=PROVIDER_NAME
        )

    solution_raw = puzzle.get("solution") or []
    if not isinstance(solution_raw, list) or not solution_raw:
        raise ChessProviderInvalidResponseError(
            f"Lichess puzzle {puzzle_id} missing solution",
            provider=PROVIDER_NAME,
        )
    solution = [str(m).strip().lower() for m in solution_raw if str(m).strip()]

    fen = str(puzzle.get("fen") or "").strip()
    if not fen:
        pgn = str(game.get("pgn") or "").strip()
        initial_ply = int(puzzle.get("initialPly") or 0)
        if not pgn:
            raise ChessProviderInvalidResponseError(
                f"Lichess puzzle {puzzle_id} missing fen and game.pgn",
                provider=PROVIDER_NAME,
            )
        fen = _derive_fen_from_game(game_pgn=pgn, initial_ply=initial_ply)

    game_id = str(game.get("id") or "").strip() or None
    themes = [str(t) for t in (puzzle.get("themes") or []) if t]
    plays = puzzle.get("plays")
    rating = puzzle.get("rating")
    perf_raw = game.get("perf")
    perf_key = perf_raw.get("key") if isinstance(perf_raw, dict) else None

    return ExternalChessPuzzle(
        provider=PROVIDER_NAME,
        external_id=puzzle_id,
        starting_fen=fen,
        solution_moves_uci=solution,
        rating=int(rating) if rating is not None else None,
        play_count=int(plays) if plays is not None else None,
        themes=themes,
        opening_tags=[],
        source_game_id=game_id,
        source_game_url=site_url(game_id) if game_id else None,
        source_metadata={
            "initial_ply": puzzle.get("initialPly"),
            "last_move": puzzle.get("lastMove"),
            "perf": perf_key,
        },
    )


class LichessPuzzlesProvider:
    """PuzzleProvider backed by Lichess site API."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._limiter = _OutboundRateLimiter(rph=settings.LICHESS_RATE_LIMIT_RPH)
        self.health = ProviderHealthState(provider=PROVIDER_NAME)

    def health_state(self) -> ProviderHealthState:
        return self.health

    async def check_health(self) -> ProviderHealthState:
        try:
            await self.get_daily_puzzle()
        except ChessProviderError as exc:
            logger.info("lichess_puzzles_health_failed detail=%s", exc)
        return self.health

    async def get_puzzle(self, puzzle_id: str) -> ExternalChessPuzzle:
        pid = puzzle_id.strip()
        if not pid:
            raise ChessProviderNotFoundError("empty puzzle id", provider=PROVIDER_NAME)

        async def _fetch() -> ExternalChessPuzzle:
            logger.info("lichess_puzzles_get id=%s", pid)
            response = await lichess_request(
                "GET",
                f"api/puzzle/{pid}",
                provider_name=PROVIDER_NAME,
                accept="application/json",
                health=self.health,
                rate_limiter=self._limiter,
                base="site",
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ChessProviderInvalidResponseError(
                    "Lichess puzzle response was not an object",
                    provider=PROVIDER_NAME,
                )
            return map_puzzle_and_game(payload)

        return await cached_model(
            key=key_puzzle(provider=PROVIDER_NAME, puzzle_id=pid),
            policy=policy_puzzle,
            model_type=ExternalChessPuzzle,
            factory=_fetch,
        )

    async def get_daily_puzzle(self) -> ExternalChessPuzzle:
        day_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async def _fetch() -> ExternalChessPuzzle:
            logger.info("lichess_puzzles_get_daily")
            response = await lichess_request(
                "GET",
                "api/puzzle/daily",
                provider_name=PROVIDER_NAME,
                accept="application/json",
                health=self.health,
                rate_limiter=self._limiter,
                base="site",
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ChessProviderInvalidResponseError(
                    "Lichess daily puzzle response was not an object",
                    provider=PROVIDER_NAME,
                )
            return map_puzzle_and_game(payload)

        return await cached_model(
            key=key_daily_puzzle(provider=PROVIDER_NAME, day_utc=day_utc),
            policy=policy_puzzle,
            model_type=ExternalChessPuzzle,
            factory=_fetch,
            ttl_seconds=daily_puzzle_ttl_seconds(),
        )
