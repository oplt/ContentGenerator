"""Chess provider registry — resolve adapters by stable name (§15).

Domain / jobs call this factory instead of constructing Lichess/Chess.com
classes ad hoc. Providers stay remote-protocol only; identity, dedupe, fame,
content opportunity, and video stay outside this package.
"""

from __future__ import annotations

from typing import Callable

from backend.modules.chess_intelligence.providers.base import (
    HistoricalGameProvider,
    PuzzleProvider,
)
from backend.modules.chess_intelligence.providers.chesscom import ChessComProvider
from backend.modules.chess_intelligence.providers.lichess_masters import (
    LichessMastersProvider,
)
from backend.modules.chess_intelligence.providers.lichess_puzzles import (
    LichessPuzzlesProvider,
)

# Conceptual ChessProvider family (prompt §15):
#   HistoricalGameProvider → lichess_masters, chesscom
#   PuzzleProvider → lichess_puzzles

_HISTORICAL_FACTORIES: dict[str, Callable[[], HistoricalGameProvider]] = {
    "lichess_masters": LichessMastersProvider,
    "chesscom": ChessComProvider,
}

_PUZZLE_FACTORIES: dict[str, Callable[[], PuzzleProvider]] = {
    "lichess_puzzles": LichessPuzzlesProvider,
}

KNOWN_HISTORICAL_PROVIDERS: frozenset[str] = frozenset(_HISTORICAL_FACTORIES)
KNOWN_PUZZLE_PROVIDERS: frozenset[str] = frozenset(_PUZZLE_FACTORIES)


class UnknownChessProviderError(ValueError):
    """Requested provider name is not registered."""


def get_historical_game_provider(name: str) -> HistoricalGameProvider:
    key = (name or "").strip().lower()
    factory = _HISTORICAL_FACTORIES.get(key)
    if factory is None:
        raise UnknownChessProviderError(
            f"Unknown historical game provider: {name!r} "
            f"(known: {sorted(KNOWN_HISTORICAL_PROVIDERS)})"
        )
    return factory()


def get_puzzle_provider(name: str = "lichess_puzzles") -> PuzzleProvider:
    key = (name or "").strip().lower() or "lichess_puzzles"
    factory = _PUZZLE_FACTORIES.get(key)
    if factory is None:
        raise UnknownChessProviderError(
            f"Unknown puzzle provider: {name!r} "
            f"(known: {sorted(KNOWN_PUZZLE_PROVIDERS)})"
        )
    return factory()
