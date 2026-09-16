"""Chess provider error types + safe HTTP mapping (Phase 21).

Distinguish failure classes for ops/metrics; never return stack traces to clients.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from backend.modules.chess_intelligence.providers.base import (
    ChessProviderAuthError,
    ChessProviderError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
    ChessProviderRateLimitedError,
    ChessProviderUnavailableError,
)
from backend.modules.chess_video.parser import ChessParseError


def http_exception_for_provider_error(exc: ChessProviderError) -> HTTPException:
    """Map provider errors to HTTP without leaking internals."""
    if isinstance(exc, ChessProviderNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ChessProviderAuthError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    if isinstance(exc, ChessProviderRateLimitedError):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": "60"},
        )
    if isinstance(exc, ChessProviderUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    if isinstance(exc, ChessProviderInvalidResponseError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    code = (
        status.HTTP_502_BAD_GATEWAY
        if not exc.retryable
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return HTTPException(status_code=code, detail=str(exc))


def http_exception_for_chess_failure(exc: Exception) -> HTTPException | None:
    """Translate known chess/domain failures; return None if not handled."""
    if isinstance(exc, ChessProviderError):
        return http_exception_for_provider_error(exc)
    if isinstance(exc, ChessParseError):
        return HTTPException(
            status_code=422,
            detail=str(exc),
        )
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database failure",
        )
    return None
