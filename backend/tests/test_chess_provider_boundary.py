"""§15 — providers stay behind registry; no domain leaks in providers/."""

from __future__ import annotations

import pytest

from backend.modules.chess_intelligence.providers.boundary import (
    DOMAIN_OWNED_CONCERNS,
    PROVIDER_OWNED_CONCERNS,
    scan_provider_domain_leaks,
)
from backend.modules.chess_intelligence.providers.registry import (
    KNOWN_HISTORICAL_PROVIDERS,
    KNOWN_PUZZLE_PROVIDERS,
    UnknownChessProviderError,
    get_historical_game_provider,
    get_puzzle_provider,
)
from backend.modules.chess_intelligence.providers.base import (
    HistoricalGameProvider,
    PuzzleProvider,
)


def test_provider_package_has_no_domain_leaks() -> None:
    assert scan_provider_domain_leaks() == []


def test_boundary_concerns_document_split() -> None:
    assert "remote protocol" in PROVIDER_OWNED_CONCERNS
    assert "canonical identity" in DOMAIN_OWNED_CONCERNS
    assert "famous status" in DOMAIN_OWNED_CONCERNS
    assert "video rendering" in DOMAIN_OWNED_CONCERNS


def test_registry_returns_protocol_instances() -> None:
    masters = get_historical_game_provider("lichess_masters")
    assert isinstance(masters, HistoricalGameProvider)
    assert masters.name == "lichess_masters"
    com = get_historical_game_provider("chesscom")
    assert isinstance(com, HistoricalGameProvider)
    puzzles = get_puzzle_provider()
    assert isinstance(puzzles, PuzzleProvider)
    assert puzzles.name == "lichess_puzzles"


def test_registry_rejects_unknown() -> None:
    with pytest.raises(UnknownChessProviderError):
        get_historical_game_provider("chessgames_scraper")
    with pytest.raises(UnknownChessProviderError):
        get_puzzle_provider("made_up")


def test_known_provider_sets() -> None:
    assert KNOWN_HISTORICAL_PROVIDERS == frozenset({"lichess_masters", "chesscom"})
    assert KNOWN_PUZZLE_PROVIDERS == frozenset({"lichess_puzzles"})
