"""Lichess Opening Explorer — masters database provider.

Official API (verified against lichess-org/api OpenAPI):
  GET https://explorer.lichess.org/masters
  GET https://explorer.lichess.org/masters/pgn/{gameId}

Auth: optional Bearer personal token (``LICHESS_API_TOKEN``). Upstream may
require a token for ``/masters`` search; PGN fetch has historically been public.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import chess

from backend.core.config import settings
from backend.modules.chess_intelligence.providers.base import (
    ChessProviderError,
    ChessProviderNotFoundError,
)
from backend.modules.chess_intelligence.providers.dtos import (
    ChessGameSearchQuery,
    ExternalChessGame,
    ExternalChessGameSummary,
)
from backend.modules.chess_intelligence.providers.lichess_http import (
    ProviderHealthState,
    _OutboundRateLimiter,
    explorer_url,
    lichess_request,
)
from backend.modules.chess_intelligence.providers.provider_cache import (
    cached_json_list,
    cached_model,
    key_game_pgn,
    key_masters_search,
    policy_pgn,
    policy_search,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "lichess_masters"
_UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$", re.IGNORECASE)
_MAX_TOP_GAMES = 15


def _winner_to_result(winner: str | None) -> str | None:
    if winner == "white":
        return "1-0"
    if winner == "black":
        return "0-1"
    if winner is None:
        return "1/2-1/2"
    return None


def _player_name(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    name = node.get("name")
    return str(name) if name else None


def _player_rating(node: Any) -> int | None:
    if not isinstance(node, dict):
        return None
    rating = node.get("rating")
    if rating is None:
        return None
    try:
        return int(rating)
    except (TypeError, ValueError):
        return None


def play_moves_param(*, moves: str | None, fen: str | None) -> str:
    """Convert query move text to Lichess ``play`` (comma-separated UCI)."""
    if not moves:
        return ""
    cleaned = re.sub(r"\{[^}]*\}", " ", moves)
    cleaned = re.sub(r"\d+\.(\.\.)?", " ", cleaned)
    cleaned = cleaned.replace(",", " ")
    tokens = [t for t in cleaned.split() if t and t not in {"1-0", "0-1", "1/2-1/2", "*"}]
    if not tokens:
        return ""
    if all(_UCI_RE.match(t) for t in tokens):
        return ",".join(t.lower() for t in tokens)

    board = chess.Board(fen) if fen else chess.Board()
    uci_moves: list[str] = []
    for token in tokens:
        try:
            move = board.parse_san(token)
        except ValueError as exc:
            raise ChessProviderError(
                f"Cannot convert move '{token}' to UCI for Lichess play param",
                provider=PROVIDER_NAME,
                retryable=False,
            ) from exc
        uci_moves.append(move.uci())
        board.push(move)
    return ",".join(uci_moves)


def map_top_game(
    raw: dict[str, Any], *, opening_eco: str | None = None
) -> ExternalChessGameSummary:
    game_id = str(raw.get("id") or "").strip()
    if not game_id:
        raise ChessProviderError("Lichess topGame missing id", provider=PROVIDER_NAME)
    year = raw.get("year")
    month = raw.get("month")
    game_date = str(month) if month else (f"{year}.01.01" if year else None)
    return ExternalChessGameSummary(
        provider=PROVIDER_NAME,
        external_id=game_id,
        white_player=_player_name(raw.get("white")),
        black_player=_player_name(raw.get("black")),
        white_rating=_player_rating(raw.get("white")),
        black_rating=_player_rating(raw.get("black")),
        year=int(year) if year is not None else None,
        game_date=game_date,
        result=_winner_to_result(raw["winner"]) if "winner" in raw else None,
        eco=opening_eco,
        source_url=explorer_url(f"masters/pgn/{game_id}"),
    )


class LichessMastersProvider:
    """Historical master games via Lichess Opening Explorer."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._limiter = _OutboundRateLimiter(rph=settings.LICHESS_RATE_LIMIT_RPH)
        self.health = ProviderHealthState(provider=PROVIDER_NAME)

    def health_state(self) -> ProviderHealthState:
        return self.health

    async def check_health(self) -> ProviderHealthState:
        """Probe masters endpoint; updates ``health``."""
        try:
            await lichess_request(
                "GET",
                "masters",
                provider_name=PROVIDER_NAME,
                params={"play": "e2e4", "topGames": 1, "moves": 0},
                health=self.health,
                rate_limiter=self._limiter,
            )
        except ChessProviderError as exc:
            logger.info("lichess_masters_health_failed detail=%s", exc)
        return self.health

    async def search_games(self, query: ChessGameSearchQuery) -> list[ExternalChessGameSummary]:
        play = play_moves_param(moves=query.moves, fen=query.fen)
        top_games = min(max(query.max_games, 1), _MAX_TOP_GAMES)
        params: dict[str, Any] = {
            "topGames": top_games,
            "moves": 0,
        }
        if play:
            params["play"] = play
        if query.fen:
            params["fen"] = query.fen
        if query.year_from is not None:
            params["since"] = query.year_from
        if query.year_to is not None:
            params["until"] = query.year_to

        cache_payload = {str(k): params[k] for k in sorted(params)}

        async def _fetch() -> list[dict[str, object]]:
            logger.info(
                "lichess_masters_search play=%s fen=%s since=%s until=%s topGames=%s",
                play or "-",
                query.fen or "-",
                query.year_from,
                query.year_to,
                top_games,
            )
            response = await lichess_request(
                "GET",
                "masters",
                provider_name=PROVIDER_NAME,
                params=params,
                health=self.health,
                rate_limiter=self._limiter,
            )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ChessProviderError(
                    "Lichess masters response was not an object",
                    provider=PROVIDER_NAME,
                )
            opening_raw = payload.get("opening")
            opening: dict[str, Any] = opening_raw if isinstance(opening_raw, dict) else {}
            eco = str(opening["eco"]) if opening.get("eco") else None
            raw_games = payload.get("topGames") or []
            if not isinstance(raw_games, list):
                raise ChessProviderError(
                    "Lichess masters topGames was not a list",
                    provider=PROVIDER_NAME,
                )
            mapped: list[dict[str, object]] = []
            for item in raw_games:
                if isinstance(item, dict):
                    mapped.append(map_top_game(item, opening_eco=eco).model_dump(mode="json"))
            return mapped

        rows = await cached_json_list(
            key=key_masters_search(cache_payload),
            policy=policy_search,
            factory=_fetch,
        )
        summaries = [ExternalChessGameSummary.model_validate(row) for row in rows]

        filtered: list[ExternalChessGameSummary] = []
        for summary in summaries:
            if query.white and query.white.lower() not in (summary.white_player or "").lower():
                continue
            if query.black and query.black.lower() not in (summary.black_player or "").lower():
                continue
            if query.player:
                needle = query.player.lower()
                white = (summary.white_player or "").lower()
                black = (summary.black_player or "").lower()
                if needle not in white and needle not in black:
                    continue
            filtered.append(summary)
        return filtered

    async def get_game(self, external_id: str) -> ExternalChessGame:
        game_id = external_id.strip()
        if not game_id:
            raise ChessProviderNotFoundError("empty game id", provider=PROVIDER_NAME)

        async def _fetch() -> ExternalChessGame:
            logger.info("lichess_masters_get_game id=%s", game_id)
            response = await lichess_request(
                "GET",
                f"masters/pgn/{game_id}",
                provider_name=PROVIDER_NAME,
                accept="application/x-chess-pgn, text/plain;q=0.9,*/*;q=0.8",
                health=self.health,
                rate_limiter=self._limiter,
            )
            pgn = (response.text or "").strip()
            if not pgn:
                raise ChessProviderNotFoundError(
                    f"empty PGN for master game {game_id}",
                    provider=PROVIDER_NAME,
                )
            # Curated provenance only — do not attach full upstream headers dump.
            return ExternalChessGame(
                provider=PROVIDER_NAME,
                external_id=game_id,
                pgn=pgn,
                source_url=explorer_url(f"masters/pgn/{game_id}"),
                source_metadata={
                    "explorer": "masters",
                    "retrieved_via": "masters/pgn",
                },
            )

        return await cached_model(
            key=key_game_pgn(provider=PROVIDER_NAME, external_id=game_id),
            policy=policy_pgn,
            model_type=ExternalChessGame,
            factory=_fetch,
        )
