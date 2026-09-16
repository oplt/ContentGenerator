"""Provider package — DTOs, Protocols, Lichess / Chess.com adapters.

Phase 20: only documented public APIs. No HTML scrapers for curated sites
(chessgames.com, etc.). Bulk Lichess puzzles use the official dataset file, not Git.
"""

from backend.modules.chess_intelligence.providers.base import (
    ChessProviderAuthError,
    ChessProviderError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
    ChessProviderRateLimitedError,
    ChessProviderUnavailableError,
    HistoricalGameProvider,
    PuzzleProvider,
)
from backend.modules.chess_intelligence.providers.chesscom import ChessComProvider
from backend.modules.chess_intelligence.providers.dtos import (
    ChessGameSearchQuery,
    ExternalChessGame,
    ExternalChessGameSummary,
    ExternalChessPuzzle,
)
from backend.modules.chess_intelligence.providers.lichess_masters import (
    LichessMastersProvider,
)
from backend.modules.chess_intelligence.providers.lichess_puzzles import (
    LichessPuzzlesProvider,
)
from backend.modules.chess_intelligence.providers.registry import (
    KNOWN_HISTORICAL_PROVIDERS,
    KNOWN_PUZZLE_PROVIDERS,
    UnknownChessProviderError,
    get_historical_game_provider,
    get_puzzle_provider,
)

__all__ = [
    "ChessComProvider",
    "ChessGameSearchQuery",
    "ChessProviderAuthError",
    "ChessProviderError",
    "ChessProviderInvalidResponseError",
    "ChessProviderNotFoundError",
    "ChessProviderRateLimitedError",
    "ChessProviderUnavailableError",
    "ExternalChessGame",
    "ExternalChessGameSummary",
    "ExternalChessPuzzle",
    "HistoricalGameProvider",
    "KNOWN_HISTORICAL_PROVIDERS",
    "KNOWN_PUZZLE_PROVIDERS",
    "LichessMastersProvider",
    "LichessPuzzlesProvider",
    "PuzzleProvider",
    "UnknownChessProviderError",
    "get_historical_game_provider",
    "get_puzzle_provider",
]
