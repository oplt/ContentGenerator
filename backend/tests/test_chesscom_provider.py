"""Chess.com PubAPI provider — mocked HTTP."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
import respx

from backend.core import http as http_mod
from backend.modules.chess_intelligence.normalizer import normalize_external_game
from backend.modules.chess_intelligence.providers import (
    ChessComProvider,
    ChessGameSearchQuery,
    ChessProviderError,
    ChessProviderNotFoundError,
    HistoricalGameProvider,
)
from backend.modules.chess_intelligence.providers.chesscom import (
    compose_external_id,
    map_game_json,
    parse_external_id,
    result_from_sides,
)

_BASE = "https://api.chess.com"

_PGN = """
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2024.01.15"]
[White "hikaru"]
[Black "opponent"]
[Result "1-0"]
[WhiteElo "3200"]
[BlackElo "2800"]

1. e4 e5 2. Nf3 1-0
"""

_GAME = {
    "url": "https://www.chess.com/game/live/999888777",
    "pgn": _PGN,
    "time_control": "600",
    "end_time": 1705334400,
    "rated": True,
    "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "time_class": "rapid",
    "rules": "chess",
    "white": {"rating": 3200, "result": "win", "username": "hikaru"},
    "black": {"rating": 2800, "result": "resigned", "username": "opponent"},
    "eco": "C42",
}


@pytest.fixture(autouse=True)
def _reset_http():
    asyncio.run(http_mod.close_http_client())
    http_mod.reset_http_stats()
    yield
    asyncio.run(http_mod.close_http_client())


def test_provider_satisfies_protocol() -> None:
    assert isinstance(ChessComProvider(), HistoricalGameProvider)


def test_result_and_external_id_helpers() -> None:
    assert result_from_sides({"result": "win"}, {"result": "resigned"}) == "1-0"
    assert result_from_sides({"result": "agreed"}, {"result": "agreed"}) == "1/2-1/2"
    assert compose_external_id("Hikaru", 2024, 1, "999") == "hikaru/2024/01/999"
    assert parse_external_id("hikaru/2024/01/999") == ("hikaru", 2024, 1, "999")


def test_map_game_json_fields() -> None:
    external = map_game_json(_GAME, username="hikaru", year=2024, month=1)
    assert external.provider == "chesscom"
    assert external.external_id == "hikaru/2024/01/999888777"
    assert external.white_player == "hikaru"
    assert external.result == "1-0"
    assert external.eco == "C42"
    assert external.source_metadata["uuid"] == _GAME["uuid"]


def test_list_archives_search_get_normalize() -> None:
    async def _run() -> None:
        provider = ChessComProvider()
        archives = {
            "archives": [
                f"{_BASE}/pub/player/hikaru/games/2023/12",
                f"{_BASE}/pub/player/hikaru/games/2024/01",
            ]
        }
        month = {"games": [_GAME]}
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/pub/player/hikaru/games/archives").mock(
                return_value=httpx.Response(200, json=archives)
            )
            router.get(f"{_BASE}/pub/player/hikaru/games/2024/01").mock(
                return_value=httpx.Response(200, json=month)
            )
            hits = await provider.search_games(
                ChessGameSearchQuery(player="hikaru", year_from=2024, max_games=5)
            )
            assert len(hits) == 1
            assert hits[0].external_id == "hikaru/2024/01/999888777"
            assert hits[0].white_player == "hikaru"
            assert provider.health.healthy is True

            external = await provider.get_game("hikaru/2024/01/999888777")
            game = normalize_external_game(tenant_id=uuid.uuid4(), external=external)
            assert game.source_provider == "chesscom"
            assert game.white_player == "hikaru"
            assert game.white_rating == 3200
            assert game.move_count >= 2

    asyncio.run(_run())


def test_search_requires_player() -> None:
    async def _run() -> None:
        with pytest.raises(ChessProviderError) as exc_info:
            await ChessComProvider().search_games(ChessGameSearchQuery(moves="e2e4"))
        assert exc_info.value.retryable is False
        assert "player" in str(exc_info.value).lower()

    asyncio.run(_run())


def test_get_game_not_found() -> None:
    async def _run() -> None:
        with respx.mock(assert_all_called=False) as router:
            router.get(f"{_BASE}/pub/player/hikaru/games/2024/01").mock(
                return_value=httpx.Response(200, json={"games": []})
            )
            with pytest.raises(ChessProviderNotFoundError):
                await ChessComProvider().get_game("hikaru/2024/01/missing")

    asyncio.run(_run())
