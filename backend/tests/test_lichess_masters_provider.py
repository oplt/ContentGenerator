"""Lichess masters provider — mocked Opening Explorer HTTP."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import respx

from backend.core import http as http_mod
from backend.modules.chess_intelligence.normalizer import normalize_external_game
from backend.modules.chess_intelligence.providers import (
    ChessGameSearchQuery,
    ChessProviderError,
    ChessProviderNotFoundError,
    HistoricalGameProvider,
    LichessMastersProvider,
)
from backend.modules.chess_intelligence.providers.lichess_masters import play_moves_param

_BASE = "https://explorer.lichess.org"
_PGN = """
[Event "Wch Blitz"]
[Site "Astana"]
[Date "2012.07.10"]
[White "Carlsen, Magnus"]
[Black "Chadaev, Nikolay"]
[Result "1-0"]
[WhiteElo "2837"]
[BlackElo "2580"]

1. e4 e5 2. f4 d5 1-0
"""

_MASTERS_PAYLOAD = {
    "opening": {"eco": "C30", "name": "King's Gambit"},
    "white": 10,
    "draws": 2,
    "black": 3,
    "moves": [],
    "topGames": [
        {
            "uci": "e2e4",
            "id": "aAbqI4ey",
            "winner": "white",
            "white": {"name": "Carlsen, Magnus", "rating": 2837},
            "black": {"name": "Chadaev, Nikolay", "rating": 2580},
            "year": 2012,
            "month": "2012-07",
        }
    ],
}


@pytest.fixture(autouse=True)
def _reset_http():
    asyncio.run(http_mod.close_http_client())
    http_mod.reset_http_stats()
    yield
    asyncio.run(http_mod.close_http_client())


def test_lichess_provider_satisfies_protocol() -> None:
    assert isinstance(LichessMastersProvider(), HistoricalGameProvider)


def test_play_moves_param_uci_and_san() -> None:
    assert play_moves_param(moves="e2e4 e7e5", fen=None) == "e2e4,e7e5"
    assert play_moves_param(moves="e2e4,e7e5", fen=None) == "e2e4,e7e5"
    assert play_moves_param(moves="1. e4 e5", fen=None) == "e2e4,e7e5"


def test_search_and_get_game_normalize() -> None:
    async def _run() -> None:
        provider = LichessMastersProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/masters").mock(
                return_value=httpx.Response(200, json=_MASTERS_PAYLOAD)
            )
            router.get(f"{_BASE}/masters/pgn/aAbqI4ey").mock(
                return_value=httpx.Response(200, text=_PGN)
            )
            hits = await provider.search_games(
                ChessGameSearchQuery(moves="e2e4", year_from=2000, max_games=5)
            )
            assert len(hits) == 1
            assert hits[0].external_id == "aAbqI4ey"
            assert hits[0].white_player == "Carlsen, Magnus"
            assert hits[0].eco == "C30"
            assert hits[0].result == "1-0"
            assert provider.health.healthy is True

            external = await provider.get_game("aAbqI4ey")
            game = normalize_external_game(tenant_id=uuid.uuid4(), external=external)
            assert game.source_provider == "lichess_masters"
            assert game.source_external_id == "aAbqI4ey"
            assert game.white_player == "Carlsen, Magnus"
            assert game.move_count >= 2
            assert game.source_metadata["explorer"] == "masters"

    asyncio.run(_run())


def test_search_unauthorized_maps_safe_error() -> None:
    async def _run() -> None:
        provider = LichessMastersProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/masters").mock(
                return_value=httpx.Response(401, text="Authorization Required")
            )
            with pytest.raises(ChessProviderError) as exc_info:
                await provider.search_games(ChessGameSearchQuery(moves="e2e4"))
            assert exc_info.value.retryable is False
            assert "LICHESS_API_TOKEN" in str(exc_info.value)
            assert provider.health.healthy is False

    asyncio.run(_run())


def test_get_game_not_found() -> None:
    async def _run() -> None:
        provider = LichessMastersProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/masters/pgn/missing").mock(
                return_value=httpx.Response(404, text="not found")
            )
            with pytest.raises(ChessProviderNotFoundError):
                await provider.get_game("missing")

    asyncio.run(_run())


def test_check_health_success() -> None:
    async def _run() -> None:
        provider = LichessMastersProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/masters").mock(
                return_value=httpx.Response(200, json=_MASTERS_PAYLOAD)
            )
            state = await provider.check_health()
            assert state.healthy is True
            assert state.last_success_at is not None

    asyncio.run(_run())
