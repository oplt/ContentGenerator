"""Lichess puzzles provider — mocked site API."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import respx

from backend.core import http as http_mod
from backend.modules.chess_intelligence.normalizer import normalize_external_puzzle
from backend.modules.chess_intelligence.providers import (
    ChessProviderNotFoundError,
    LichessPuzzlesProvider,
    PuzzleProvider,
)
from backend.modules.chess_intelligence.providers.lichess_puzzles import map_puzzle_and_game
from backend.modules.chess_video.parser import ChessParseError

_BASE = "https://lichess.org"

_DAILY_PAYLOAD = {
    "game": {
        "id": "7xrHOf1n",
        "perf": {"key": "classical", "name": "Classical"},
        "pgn": "e4 c5 Nf3",
    },
    "puzzle": {
        "id": "m5h82",
        "rating": 2054,
        "plays": 90899,
        "solution": ["e2e4"],
        "themes": ["mate", "short"],
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "lastMove": "c4c5",
        "initialPly": 0,
    },
}


@pytest.fixture(autouse=True)
def _reset_http():
    asyncio.run(http_mod.close_http_client())
    http_mod.reset_http_stats()
    yield
    asyncio.run(http_mod.close_http_client())


def test_provider_satisfies_protocol() -> None:
    assert isinstance(LichessPuzzlesProvider(), PuzzleProvider)


def test_map_puzzle_and_game_curated_fields() -> None:
    external = map_puzzle_and_game(_DAILY_PAYLOAD)
    assert external.provider == "lichess_puzzles"
    assert external.external_id == "m5h82"
    assert external.rating == 2054
    assert external.play_count == 90899
    assert external.themes == ["mate", "short"]
    assert external.source_game_id == "7xrHOf1n"
    assert external.source_game_url.endswith("/7xrHOf1n")
    assert external.solution_moves_uci == ["e2e4"]


def test_get_daily_and_normalize() -> None:
    async def _run() -> None:
        provider = LichessPuzzlesProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/api/puzzle/daily").mock(
                return_value=httpx.Response(200, json=_DAILY_PAYLOAD)
            )
            external = await provider.get_daily_puzzle()
            puzzle = normalize_external_puzzle(
                tenant_id=uuid.uuid4(),
                external=external,
            )
            assert puzzle.provider == "lichess_puzzles"
            assert puzzle.external_id == "m5h82"
            assert puzzle.solution_moves_san == ["e4"]
            assert puzzle.rating == 2054
            assert provider.health.healthy is True

    asyncio.run(_run())


def test_get_puzzle_by_id_not_found() -> None:
    async def _run() -> None:
        provider = LichessPuzzlesProvider()
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/api/puzzle/missing").mock(
                return_value=httpx.Response(404, json={"error": "Not found"})
            )
            with pytest.raises(ChessProviderNotFoundError):
                await provider.get_puzzle("missing")

    asyncio.run(_run())


def test_normalize_rejects_illegal_solution_from_provider() -> None:
    external = map_puzzle_and_game(
        {
            "game": {"id": "g1"},
            "puzzle": {
                "id": "bad",
                "rating": 1000,
                "plays": 1,
                "solution": ["e2e5"],
                "themes": [],
                "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            },
        }
    )
    with pytest.raises(ChessParseError):
        normalize_external_puzzle(tenant_id=uuid.uuid4(), external=external)
