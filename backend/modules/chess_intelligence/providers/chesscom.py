"""Chess.com PubAPI provider — modern online games (not historical OTB).

  GET /pub/player/{user}/games/archives
  GET /pub/player/{user}/games/{YYYY}/{MM}

``get_game`` external_id: ``{username}/{YYYY}/{MM}/{game_key}``
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from backend.core.config import settings
from backend.modules.chess_intelligence.providers.base import (
    ChessProviderError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
)
from backend.modules.chess_intelligence.providers.chesscom_http import (
    PROVIDER_NAME,
    chesscom_request,
)
from backend.modules.chess_intelligence.providers.dtos import (
    ChessGameSearchQuery,
    ExternalChessGame,
    ExternalChessGameSummary,
)
from backend.modules.chess_intelligence.providers.lichess_http import (
    ProviderHealthState,
    _OutboundRateLimiter,
)
from backend.modules.chess_intelligence.providers.provider_cache import (
    cached_json_list,
    cached_model,
    key_game_pgn,
    key_month_archive,
    key_provider_meta,
    policy_meta,
    policy_pgn,
)

logger = logging.getLogger(__name__)

_ARCHIVE_RE = re.compile(r"/pub/player/([^/]+)/games/(\d{4})/(\d{2})/?$", re.I)
_GAME_URL_ID_RE = re.compile(r"/game/(?:live|daily)/(\d+)", re.I)
_EXTERNAL_ID_RE = re.compile(r"^([^/]+)/(\d{4})/(\d{1,2})/([^/]+)$")
_DRAW = frozenset(
    {"agreed", "stalemate", "repetition", "insufficient", "50move", "timevsinsufficient"}
)
_MAX_ARCHIVE_FETCHES = 12


def _side(node: Any) -> dict[str, Any]:
    return node if isinstance(node, dict) else {}


def _uname(node: Any) -> str | None:
    name = _side(node).get("username")
    return str(name) if name else None


def _rating(node: Any) -> int | None:
    raw = _side(node).get("rating")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def result_from_sides(white: Any, black: Any) -> str | None:
    wr = str(_side(white).get("result") or "").lower()
    br = str(_side(black).get("result") or "").lower()
    if wr == "win":
        return "1-0"
    if br == "win":
        return "0-1"
    if wr in _DRAW or br in _DRAW:
        return "1/2-1/2"
    return None


def game_key_from_raw(raw: dict[str, Any]) -> str:
    match = _GAME_URL_ID_RE.search(str(raw.get("url") or ""))
    if match:
        return match.group(1)
    uuid_val = str(raw.get("uuid") or "").strip()
    if uuid_val:
        return uuid_val
    raise ChessProviderInvalidResponseError(
        "Chess.com game missing id", provider=PROVIDER_NAME
    )


def compose_external_id(username: str, year: int, month: int, game_key: str) -> str:
    return f"{username.lower()}/{year:04d}/{month:02d}/{game_key}"


def parse_external_id(external_id: str) -> tuple[str, int, int, str]:
    match = _EXTERNAL_ID_RE.match(external_id.strip())
    if not match:
        raise ChessProviderError(
            "Chess.com external_id must be username/YYYY/MM/game_key",
            provider=PROVIDER_NAME,
            retryable=False,
        )
    user, y, m, key = match.groups()
    return user.lower(), int(y), int(m), key


def parse_archive_url(url: str) -> tuple[str, int, int] | None:
    match = _ARCHIVE_RE.search(url.strip())
    if not match:
        return None
    user, y, m = match.groups()
    return user.lower(), int(y), int(m)


def map_game_json(
    raw: dict[str, Any], *, username: str, year: int, month: int
) -> ExternalChessGame:
    pgn = str(raw.get("pgn") or "").strip()
    if not pgn:
        raise ChessProviderInvalidResponseError(
            "Chess.com game missing pgn", provider=PROVIDER_NAME
        )
    key = game_key_from_raw(raw)
    white, black = raw.get("white"), raw.get("black")
    end_time = raw.get("end_time")
    game_date = None
    if isinstance(end_time, (int, float)):
        game_date = datetime.fromtimestamp(int(end_time), tz=timezone.utc).strftime("%Y.%m.%d")
    return ExternalChessGame(
        provider=PROVIDER_NAME,
        external_id=compose_external_id(username, year, month, key),
        pgn=pgn,
        white_player=_uname(white),
        black_player=_uname(black),
        white_rating=_rating(white),
        black_rating=_rating(black),
        event=str(raw["time_class"]) if raw.get("time_class") else None,
        site="Chess.com",
        game_date=game_date,
        year=year,
        result=result_from_sides(white, black),
        eco=str(raw["eco"]) if raw.get("eco") else None,
        source_url=str(raw.get("url") or "") or None,
        source_metadata={
            "time_class": raw.get("time_class"),
            "time_control": raw.get("time_control"),
            "rated": raw.get("rated"),
            "rules": raw.get("rules"),
            "uuid": raw.get("uuid"),
        },
    )


def _matches_query(game: ExternalChessGame, query: ChessGameSearchQuery) -> bool:
    if query.white and query.white.lower() not in (game.white_player or "").lower():
        return False
    if query.black and query.black.lower() not in (game.black_player or "").lower():
        return False
    if query.moves:
        tokens = [t for t in query.moves.lower().replace(",", " ").split() if len(t) >= 4]
        body = game.pgn.lower()
        if tokens and not all(t in body for t in tokens):
            return False
    return True


class ChessComProvider:
    """Online player games via Chess.com PubAPI."""

    name = PROVIDER_NAME

    def __init__(self) -> None:
        self._limiter = _OutboundRateLimiter(rph=settings.CHESSCOM_RATE_LIMIT_RPH)
        self.health = ProviderHealthState(provider=PROVIDER_NAME)

    async def check_health(self) -> ProviderHealthState:
        try:
            await chesscom_request(
                "pub/player/hikaru", health=self.health, rate_limiter=self._limiter
            )
        except ChessProviderError as exc:
            logger.info("chesscom_health_failed detail=%s", exc)
        return self.health

    async def list_archives(self, username: str) -> list[str]:
        user = username.strip().lower()
        if not user:
            raise ChessProviderError("username required", provider=PROVIDER_NAME, retryable=False)

        async def _fetch() -> list[dict[str, object]]:
            response = await chesscom_request(
                f"pub/player/{user}/games/archives",
                health=self.health,
                rate_limiter=self._limiter,
            )
            payload = response.json()
            archives = payload.get("archives") if isinstance(payload, dict) else None
            if not isinstance(archives, list):
                raise ChessProviderInvalidResponseError(
                    "Chess.com archives invalid", provider=PROVIDER_NAME
                )
            return [{"url": str(u)} for u in archives if u]

        rows = await cached_json_list(
            key=key_provider_meta(
                provider=PROVIDER_NAME, kind="archives", identity=user
            ),
            policy=policy_meta,
            factory=_fetch,
        )
        return [str(row["url"]) for row in rows if row.get("url")]

    async def get_games_for_month(
        self, username: str, year: int, month: int
    ) -> list[ExternalChessGame]:
        user = username.strip().lower()
        if not user:
            raise ChessProviderError("username required", provider=PROVIDER_NAME, retryable=False)
        if not 1 <= month <= 12:
            raise ChessProviderError("month must be 1-12", provider=PROVIDER_NAME, retryable=False)

        async def _fetch() -> list[dict[str, object]]:
            response = await chesscom_request(
                f"pub/player/{user}/games/{year:04d}/{month:02d}",
                health=self.health,
                rate_limiter=self._limiter,
            )
            payload = response.json()
            raw_games = payload.get("games") if isinstance(payload, dict) else None
            if not isinstance(raw_games, list):
                raise ChessProviderInvalidResponseError(
                    "Chess.com month games invalid", provider=PROVIDER_NAME
                )
            out: list[dict[str, object]] = []
            for item in raw_games:
                if isinstance(item, dict):
                    try:
                        out.append(
                            map_game_json(item, username=user, year=year, month=month).model_dump(
                                mode="json"
                            )
                        )
                    except ChessProviderError:
                        continue
            return out

        rows = await cached_json_list(
            key=key_month_archive(
                provider=PROVIDER_NAME, username=user, year=year, month=month
            ),
            policy=policy_pgn,
            factory=_fetch,
        )
        return [ExternalChessGame.model_validate(row) for row in rows]

    async def get_game(self, external_id: str) -> ExternalChessGame:
        user, year, month, key = parse_external_id(external_id)
        want = compose_external_id(user, year, month, key)

        async def _fetch() -> ExternalChessGame:
            for game in await self.get_games_for_month(user, year, month):
                if game.external_id == want:
                    return game
                if str((game.source_metadata or {}).get("uuid") or "") == key:
                    return game
            raise ChessProviderNotFoundError(
                f"Chess.com game not found: {external_id}",
                provider=PROVIDER_NAME,
            )

        return await cached_model(
            key=key_game_pgn(provider=PROVIDER_NAME, external_id=want),
            policy=policy_pgn,
            model_type=ExternalChessGame,
            factory=_fetch,
        )

    async def search_games(self, query: ChessGameSearchQuery) -> list[ExternalChessGameSummary]:
        user = (query.player or "").strip().lower()
        if not user:
            raise ChessProviderError(
                "Chess.com search requires query.player (username)",
                provider=PROVIDER_NAME,
                retryable=False,
            )
        archives = await self.list_archives(user)
        months: list[tuple[int, int]] = []
        for url in reversed(archives):
            parsed = parse_archive_url(url)
            if parsed is None:
                continue
            _u, year, month = parsed
            if query.year_from is not None and year < query.year_from:
                continue
            if query.year_to is not None and year > query.year_to:
                continue
            months.append((year, month))
            if len(months) >= _MAX_ARCHIVE_FETCHES:
                break

        limit = min(max(query.max_games, 1), 100)
        hits: list[ExternalChessGameSummary] = []
        for year, month in months:
            if len(hits) >= limit:
                break
            for game in reversed(await self.get_games_for_month(user, year, month)):
                if not _matches_query(game, query):
                    continue
                hits.append(
                    ExternalChessGameSummary(
                        provider=game.provider,
                        external_id=game.external_id,
                        white_player=game.white_player,
                        black_player=game.black_player,
                        white_rating=game.white_rating,
                        black_rating=game.black_rating,
                        year=game.year,
                        game_date=game.game_date,
                        event=game.event,
                        result=game.result,
                        eco=game.eco,
                        source_url=game.source_url,
                    )
                )
                if len(hits) >= limit:
                    break
        return hits
