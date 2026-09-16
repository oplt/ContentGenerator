"""Chess.com PubAPI HTTP helpers (rate limit, errors, User-Agent)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

from backend.core.config import settings
from backend.core.http import build_timeout, request
from backend.modules.chess_intelligence.observability import log_provider_request
from backend.modules.chess_intelligence.providers.base import (
    ChessProviderAuthError,
    ChessProviderError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
    ChessProviderRateLimitedError,
    ChessProviderUnavailableError,
)
from backend.modules.chess_intelligence.providers.lichess_http import (
    ProviderHealthState,
    _OutboundRateLimiter,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "chesscom"
PROVIDER_HTTP_KEY = "chesscom"


def chesscom_url(path: str) -> str:
    base = settings.CHESSCOM_API_BASE_URL.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": settings.CHESSCOM_USER_AGENT.strip()
        or f"{settings.APP_NAME}/chess-intelligence",
    }


def map_http_error(response: httpx.Response, action: str) -> ChessProviderError:
    status = response.status_code
    preview = (response.text or "")[:200].strip()
    if status == 404:
        return ChessProviderNotFoundError(
            f"Chess.com {action} not found ({status})",
            provider=PROVIDER_NAME,
        )
    if status in {401, 403}:
        return ChessProviderAuthError(
            f"Chess.com {action} unauthorized ({status}). Check User-Agent / access.",
            provider=PROVIDER_NAME,
        )
    if status == 429:
        return ChessProviderRateLimitedError(
            f"Chess.com {action} rate limited ({status}).",
            provider=PROVIDER_NAME,
        )
    if status >= 500:
        return ChessProviderUnavailableError(
            f"Chess.com {action} unavailable ({status}). {preview}",
            provider=PROVIDER_NAME,
        )
    if 400 <= status < 500:
        return ChessProviderInvalidResponseError(
            f"Chess.com {action} rejected ({status}). {preview}",
            provider=PROVIDER_NAME,
        )
    return ChessProviderUnavailableError(
        f"Chess.com {action} unexpected status ({status})",
        provider=PROVIDER_NAME,
    )


def _mark_failure(health: ProviderHealthState, message: str) -> None:
    health.healthy = False
    health.detail = message
    health.last_error = message
    health.last_error_at = datetime.now(timezone.utc)
    health.consecutive_failures += 1


def _mark_success(health: ProviderHealthState) -> None:
    health.healthy = True
    health.detail = None
    health.last_success_at = datetime.now(timezone.utc)
    health.consecutive_failures = 0
    health.last_error = None


async def chesscom_request(
    path: str,
    *,
    health: ProviderHealthState | None = None,
    rate_limiter: _OutboundRateLimiter | None = None,
) -> httpx.Response:
    """Chess.com GET via shared client (timeouts, retries, 429 backoff)."""
    if rate_limiter is not None:
        await rate_limiter.acquire()
    started = time.perf_counter()
    try:
        response = await request(
            "GET",
            chesscom_url(path),
            provider=PROVIDER_HTTP_KEY,
            max_retries=settings.CHESSCOM_HTTP_MAX_RETRIES,
            timeout=build_timeout(
                connect=min(5.0, settings.CHESSCOM_HTTP_TIMEOUT_SECONDS),
                read=settings.CHESSCOM_HTTP_TIMEOUT_SECONDS,
            ),
            headers=_headers(),
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        log_provider_request(
            provider=PROVIDER_NAME,
            action=path,
            outcome="transport_error",
            duration_ms=duration_ms,
            status_class="transport",
            error_class=type(exc).__name__,
        )
        logger.warning(
            "chesscom_transport_error provider=%s path=%s error=%s",
            PROVIDER_NAME,
            path,
            exc,
        )
        if health is not None:
            _mark_failure(health, str(exc))
        raise ChessProviderUnavailableError(
            f"Chess.com transport error: {exc}",
            provider=PROVIDER_NAME,
        ) from exc

    duration_ms = (time.perf_counter() - started) * 1000.0
    if response.status_code >= 400:
        err = map_http_error(response, path)
        status_class = f"{response.status_code // 100}xx"
        outcome = "failure" if response.status_code >= 500 else "client_error"
        log_provider_request(
            provider=PROVIDER_NAME,
            action=path,
            outcome=outcome,
            duration_ms=duration_ms,
            status_class=status_class,
            error_class=err.code,
        )
        logger.warning(
            "chesscom_http_error provider=%s path=%s status=%s code=%s retryable=%s",
            PROVIDER_NAME,
            path,
            response.status_code,
            err.code,
            err.retryable,
        )
        if health is not None:
            _mark_failure(health, str(err))
        raise err
    log_provider_request(
        provider=PROVIDER_NAME,
        action=path,
        outcome="success",
        duration_ms=duration_ms,
        status_class=f"{response.status_code // 100}xx",
    )
    if health is not None:
        _mark_success(health)
    return response
