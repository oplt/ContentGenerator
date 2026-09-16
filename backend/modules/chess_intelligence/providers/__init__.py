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
    "LichessMastersProvider",
    "LichessPuzzlesProvider",
    "PuzzleProvider",
]
