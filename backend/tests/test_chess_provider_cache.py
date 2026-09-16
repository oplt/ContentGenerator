"""Phase 22 — chess provider TenantCache strategy."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx

from backend.core import http as http_mod
from backend.core.tenant_cache import OWNER_CHESS, TenantCache, build_cache_key, reset_cache_stats
from backend.modules.chess_intelligence.providers.chesscom import ChessComProvider
from backend.modules.chess_intelligence.providers.dtos import ChessGameSearchQuery
from backend.modules.chess_intelligence.providers.lichess_masters import LichessMastersProvider
from backend.modules.chess_intelligence.providers.lichess_puzzles import LichessPuzzlesProvider
from backend.modules.chess_intelligence.providers.provider_cache import (
    daily_puzzle_ttl_seconds,
    key_daily_puzzle,
    key_game_pgn,
    key_masters_search,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, seconds: int, value: str):
        self.store[key] = value
        return True

    async def set(self, key: str, value: str, **kwargs):
        if kwargs.get("nx") and key in self.store:
            return False
        self.store[key] = value
        return True

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
        return deleted

    async def eval(self, script: str, numkeys: int, *args):
        key, token = args[0], args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0

    async def scan_iter(self, match: str = "*", count: int = 100):
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


class _FakeBackend:
    def __init__(self) -> None:
        self.redis_client = _FakeRedis()

    async def delete(self, *keys: str):
        return bool(await self.redis_client.delete(*keys))


_MASTERS = {
    "opening": {"eco": "C30", "name": "King's Gambit"},
    "topGames": [
        {
            "id": "cacheGame1",
            "winner": "white",
            "white": {"name": "A", "rating": 2800},
            "black": {"name": "B", "rating": 2700},
            "year": 2012,
        }
    ],
}
_PGN = '[Event "T"]\n[Result "1-0"]\n\n1. e4 e5 1-0\n'
_PUZZLE = {
    "game": {"id": "g1", "perf": {"key": "blitz"}, "pgn": "e4"},
    "puzzle": {
        "id": "pz1",
        "rating": 1500,
        "plays": 10,
        "solution": ["e2e4"],
        "themes": ["mate"],
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "initialPly": 0,
    },
}


@pytest.fixture()
def fake_cache():
    reset_cache_stats()
    cache = TenantCache(backend=_FakeBackend())
    with patch(
        "backend.modules.chess_intelligence.providers.provider_cache.tenant_cache",
        cache,
    ):
        yield cache


@pytest.fixture(autouse=True)
def _reset_http():
    asyncio.run(http_mod.close_http_client())
    http_mod.reset_http_stats()
    yield
    asyncio.run(http_mod.close_http_client())


def test_owner_and_keys_are_global() -> None:
    assert OWNER_CHESS == "chess_intelligence"
    search = key_masters_search({"play": "e2e4", "topGames": 1})
    pgn = key_game_pgn(provider="lichess_masters", external_id="AbC")
    daily = key_daily_puzzle(provider="lichess_puzzles", day_utc="2026-09-16")
    assert ":global:chess_intelligence:" in search
    assert pgn.endswith(":lichess_masters:pgn:abc") or "lichess_masters:pgn:abc" in pgn
    assert "daily:2026-09-16" in daily
    assert build_cache_key(
        owner=OWNER_CHESS, identity="x", global_scope=True
    ).startswith("cg:")


def test_daily_puzzle_ttl_clamps_to_next_utc_midnight() -> None:
    now = datetime(2026, 9, 16, 23, 50, tzinfo=timezone.utc)
    ttl = daily_puzzle_ttl_seconds(now=now)
    assert 60 <= ttl <= 900  # ~15m to 00:05 UTC next day, under ceiling


def test_masters_search_and_pgn_cache_second_call(fake_cache: TenantCache) -> None:
    async def _run() -> None:
        provider = LichessMastersProvider()
        with respx.mock(assert_all_called=True) as router:
            search_route = router.get("https://explorer.lichess.org/masters").mock(
                return_value=httpx.Response(200, json=_MASTERS)
            )
            pgn_route = router.get("https://explorer.lichess.org/masters/pgn/cacheGame1").mock(
                return_value=httpx.Response(200, text=_PGN)
            )
            hits1 = await provider.search_games(ChessGameSearchQuery(moves="e2e4", max_games=5))
            hits2 = await provider.search_games(ChessGameSearchQuery(moves="e2e4", max_games=5))
            assert hits1[0].external_id == hits2[0].external_id == "cacheGame1"
            assert search_route.call_count == 1

            g1 = await provider.get_game("cacheGame1")
            g2 = await provider.get_game("cacheGame1")
            assert g1.pgn == g2.pgn
            assert pgn_route.call_count == 1

    asyncio.run(_run())


def test_daily_and_puzzle_cache(fake_cache: TenantCache) -> None:
    async def _run() -> None:
        provider = LichessPuzzlesProvider()
        with respx.mock(assert_all_called=True) as router:
            daily_route = router.get("https://lichess.org/api/puzzle/daily").mock(
                return_value=httpx.Response(200, json=_PUZZLE)
            )
            id_route = router.get("https://lichess.org/api/puzzle/pz1").mock(
                return_value=httpx.Response(200, json=_PUZZLE)
            )
            d1 = await provider.get_daily_puzzle()
            d2 = await provider.get_daily_puzzle()
            assert d1.external_id == d2.external_id == "pz1"
            assert daily_route.call_count == 1

            p1 = await provider.get_puzzle("pz1")
            p2 = await provider.get_puzzle("pz1")
            assert p1.external_id == p2.external_id
            assert id_route.call_count == 1

    asyncio.run(_run())


def test_chesscom_archives_and_month_cache(fake_cache: TenantCache) -> None:
    async def _run() -> None:
        provider = ChessComProvider()
        archives = {
            "archives": ["https://api.chess.com/pub/player/hikaru/games/2024/01"]
        }
        month = {
            "games": [
                {
                    "url": "https://www.chess.com/game/live/111",
                    "pgn": _PGN,
                    "end_time": 1705334400,
                    "uuid": "u1",
                    "time_class": "rapid",
                    "white": {"rating": 3000, "result": "win", "username": "hikaru"},
                    "black": {"rating": 2800, "result": "resigned", "username": "x"},
                }
            ]
        }
        with respx.mock(assert_all_called=True) as router:
            arch = router.get("https://api.chess.com/pub/player/hikaru/games/archives").mock(
                return_value=httpx.Response(200, json=archives)
            )
            mon = router.get("https://api.chess.com/pub/player/hikaru/games/2024/01").mock(
                return_value=httpx.Response(200, json=month)
            )
            a1 = await provider.list_archives("hikaru")
            a2 = await provider.list_archives("hikaru")
            assert a1 == a2
            assert arch.call_count == 1

            g1 = await provider.get_games_for_month("hikaru", 2024, 1)
            g2 = await provider.get_games_for_month("hikaru", 2024, 1)
            assert len(g1) == len(g2) == 1
            assert mon.call_count == 1

            ext = await provider.get_game("hikaru/2024/01/111")
            assert ext.external_id == "hikaru/2024/01/111"
            # month already cached; individual get_game may still store per-game key
            assert mon.call_count == 1

    asyncio.run(_run())


def test_catalog_prefer_skips_provider_when_row_exists() -> None:
    async def _run() -> None:
        from backend.modules.chess_intelligence.catalog_prefer import (
            get_external_game_prefer_catalog,
        )
        from backend.modules.chess_intelligence.models import ChessGame

        class _Prov:
            name = "lichess_masters"
            called = False

            async def get_game(self, external_id: str):  # noqa: ARG002
                self.called = True
                raise AssertionError("provider must not be called")

        game = ChessGame(
            id=uuid4(),
            tenant_id=uuid4(),
            game_fingerprint="fp",
            content_hash="ch",
            normalized_pgn=_PGN,
            starting_fen="start",
            source_provider="lichess_masters",
            source_external_id="abc",
        )

        class _FakeRepo:
            async def get_by_provider_external_id(self, **kwargs):  # noqa: ANN003
                return game

        with patch(
            "backend.modules.chess_intelligence.catalog_prefer.ChessGameRepository",
            lambda db: _FakeRepo(),  # noqa: ARG005
        ):
            result = await get_external_game_prefer_catalog(
                db=None,  # type: ignore[arg-type]
                tenant_id=game.tenant_id,
                provider=_Prov(),  # type: ignore[arg-type]
                external_id="abc",
            )
        assert result is game
        assert _Prov.called is False

    asyncio.run(_run())
