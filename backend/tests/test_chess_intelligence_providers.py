"""Phase 2 provider interface: Protocols, DTOs, normalize path."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from backend.modules.chess_intelligence.normalizer import (
    normalize_external_game,
    normalize_external_puzzle,
)
from backend.modules.chess_intelligence.providers import (
    ChessGameSearchQuery,
    ChessProviderNotFoundError,
    ExternalChessGame,
    ExternalChessGameSummary,
    ExternalChessPuzzle,
    HistoricalGameProvider,
    PuzzleProvider,
)
from backend.modules.chess_video.parser import ChessParseError

_PGN = """
[Event "Test"]
[White "Alpha"]
[Black "Beta"]
[Result "1-0"]
[Date "1990.01.01"]

1. e4 e5 2. Nf3 1-0
"""


class _FakeHistoricalProvider:
    name = "fake_masters"

    def __init__(self) -> None:
        self._games = {
            "g1": ExternalChessGame(
                provider="fake_masters",
                external_id="g1",
                pgn=_PGN,
                white_rating=2700,
                source_url="https://example.test/g1",
                source_metadata={"opening_explorer": True},
            )
        }

    async def search_games(self, query: ChessGameSearchQuery) -> list[ExternalChessGameSummary]:
        hits = [
            ExternalChessGameSummary(
                provider="fake_masters",
                external_id="g1",
                white_player="Alpha",
                black_player="Beta",
                year=1990,
                result="1-0",
            )
        ]
        if query.year_from and query.year_from > 1990:
            return []
        return hits[: query.max_games]

    async def get_game(self, external_id: str) -> ExternalChessGame:
        game = self._games.get(external_id)
        if game is None:
            raise ChessProviderNotFoundError(
                f"game {external_id} not found",
                provider=self.name,
            )
        return game


class _FakePuzzleProvider:
    name = "fake_puzzles"

    async def get_puzzle(self, puzzle_id: str) -> ExternalChessPuzzle:
        if puzzle_id != "p1":
            raise ChessProviderNotFoundError("missing", provider=self.name)
        return ExternalChessPuzzle(
            provider="fake_puzzles",
            external_id="p1",
            starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            solution_moves_uci=["e2e4"],
            rating=800,
            themes=["mateIn1"],
        )

    async def get_daily_puzzle(self) -> ExternalChessPuzzle:
        return await self.get_puzzle("p1")


def test_fake_providers_satisfy_protocols() -> None:
    assert isinstance(_FakeHistoricalProvider(), HistoricalGameProvider)
    assert isinstance(_FakePuzzleProvider(), PuzzleProvider)


def test_historical_provider_search_and_get_normalize() -> None:
    async def _run() -> None:
        provider: HistoricalGameProvider = _FakeHistoricalProvider()
        hits = await provider.search_games(ChessGameSearchQuery(moves="e2e4", max_games=5))
        assert len(hits) == 1
        assert hits[0].external_id == "g1"

        external = await provider.get_game("g1")
        tenant_id = uuid.uuid4()
        game = normalize_external_game(tenant_id=tenant_id, external=external)
        assert game.source_provider == "fake_masters"
        assert game.source_external_id == "g1"
        assert game.white_player == "Alpha"
        assert game.white_rating == 2700
        assert game.move_count == 3
        assert game.source_metadata == {"opening_explorer": True}
        assert '[White "Alpha"]' in game.normalized_pgn

    asyncio.run(_run())


def test_historical_provider_not_found() -> None:
    async def _run() -> None:
        provider = _FakeHistoricalProvider()
        with pytest.raises(ChessProviderNotFoundError):
            await provider.get_game("missing")

    asyncio.run(_run())


def test_puzzle_provider_normalize_derives_san() -> None:
    async def _run() -> None:
        provider: PuzzleProvider = _FakePuzzleProvider()
        external = await provider.get_daily_puzzle()
        puzzle = normalize_external_puzzle(tenant_id=uuid.uuid4(), external=external)
        assert puzzle.provider == "fake_puzzles"
        assert puzzle.solution_moves_san == ["e4"]
        assert puzzle.rating == 800
        assert puzzle.themes == ["mateIn1"]

    asyncio.run(_run())


def test_normalize_rejects_illegal_puzzle_solution() -> None:
    external = ExternalChessPuzzle(
        provider="fake",
        external_id="bad",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        solution_moves_uci=["e2e5"],  # illegal
    )
    with pytest.raises(ChessParseError):
        normalize_external_puzzle(tenant_id=uuid.uuid4(), external=external)


def test_search_query_strips_blank_moves() -> None:
    q = ChessGameSearchQuery(moves="  ")
    assert q.moves is None
