"""Provider-independent retrieval contracts + typed errors.

Conceptual ChessProvider family (§15)::

    HistoricalGameProvider  — remote historical game search/fetch
    PuzzleProvider          — remote puzzle fetch

Adapters live beside this module (Lichess / Chess.com). Domain code resolves
them via ``providers.registry`` and must not teach providers about dedupe,
fame, content opportunity, or video.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.modules.chess_intelligence.providers.dtos import (
    ChessGameSearchQuery,
    ExternalChessGame,
    ExternalChessGameSummary,
    ExternalChessPuzzle,
)


class ChessProviderError(Exception):
    """Base error for chess provider adapters (safe to map to HTTP)."""

    code: str = "provider_error"

    def __init__(self, message: str, *, provider: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ChessProviderNotFoundError(ChessProviderError):
    """Requested external game/puzzle does not exist."""

    code = "not_found"


class ChessProviderAuthError(ChessProviderError):
    """Upstream rejected credentials / missing token (401/403)."""

    code = "authentication_failure"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=False)


class ChessProviderRateLimitedError(ChessProviderError):
    """Upstream 429 after shared-client retries exhausted."""

    code = "rate_limited"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=True)


class ChessProviderUnavailableError(ChessProviderError):
    """Transient upstream failure (timeout, 5xx)."""

    code = "provider_unavailable"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=True)


class ChessProviderInvalidResponseError(ChessProviderError):
    """Upstream payload missing required fields / wrong shape."""

    code = "invalid_provider_response"

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message, provider=provider, retryable=False)


@runtime_checkable
class HistoricalGameProvider(Protocol):
    """Retrieve historical games from an external source."""

    @property
    def name(self) -> str:
        """Stable provider id (e.g. ``lichess_masters``)."""
        ...

    async def search_games(
        self,
        query: ChessGameSearchQuery,
    ) -> list[ExternalChessGameSummary]: ...

    async def get_game(
        self,
        external_id: str,
    ) -> ExternalChessGame: ...


@runtime_checkable
class PuzzleProvider(Protocol):
    """Retrieve puzzles from an external source."""

    @property
    def name(self) -> str:
        """Stable provider id (e.g. ``lichess_puzzles``)."""
        ...

    async def get_puzzle(
        self,
        puzzle_id: str,
    ) -> ExternalChessPuzzle: ...

    async def get_daily_puzzle(self) -> ExternalChessPuzzle: ...
