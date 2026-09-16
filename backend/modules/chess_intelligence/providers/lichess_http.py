"""Shared Lichess explorer HTTP helpers (rate limit, auth, error mapping)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
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

logger = logging.getLogger(__name__)

PROVIDER_HTTP_KEY = "lichess"


@dataclass
class ProviderHealthState:
    provider: str
    healthy: bool = True
    detail: str | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0


@dataclass
class _OutboundRateLimiter:
    """Sliding-window limiter: at most ``rph`` requests per rolling hour."""

    rph: int
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _timestamps: list[float] = field(default_factory=list)

    async def acquire(self) -> None:
        limit = max(self.rph, 1)
        window = 3600.0
        async with self._lock:
            while True:
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < window]
                if len(self._timestamps) < limit:
                    self._timestamps.append(now)
                    return
                wait = window - (now - self._timestamps[0]) + 0.01
                await asyncio.sleep(max(wait, 0.01))


def explorer_base_url() -> str:
    return settings.LICHESS_EXPLORER_BASE_URL.rstrip("/") + "/"


def explorer_url(path: str) -> str:
    return urljoin(explorer_base_url(), path.lstrip("/"))


def site_base_url() -> str:
    return settings.LICHESS_API_BASE_URL.rstrip("/") + "/"


def site_url(path: str) -> str:
    return urljoin(site_base_url(), path.lstrip("/"))


def auth_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, application/x-chess-pgn, text/plain;q=0.9,*/*;q=0.8",
        "User-Agent": f"{settings.APP_NAME}/chess-intelligence",
    }
    token = (settings.LICHESS_API_TOKEN or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def map_http_error(*, provider: str, response: httpx.Response, action: str) -> ChessProviderError:
    status = response.status_code
    body_preview = (response.text or "")[:200].strip()
    if status == 404:
        return ChessProviderNotFoundError(
            f"Lichess {action} not found ({status})",
            provider=provider,
        )
    if status in {401, 403}:
        return ChessProviderAuthError(
            f"Lichess {action} unauthorized ({status}); set LICHESS_API_TOKEN if required.",
            provider=provider,
        )
    if status == 429:
        return ChessProviderRateLimitedError(
            f"Lichess {action} rate limited ({status}).",
            provider=provider,
        )
    if status >= 500:
        return ChessProviderUnavailableError(
            f"Lichess {action} unavailable ({status}). {body_preview}",
            provider=provider,
        )
    if 400 <= status < 500:
        return ChessProviderInvalidResponseError(
            f"Lichess {action} rejected ({status}). {body_preview}",
            provider=provider,
        )
    return ChessProviderUnavailableError(
        f"Lichess {action} unexpected status ({status})",
        provider=provider,
    )


async def lichess_request(
    method: str,
    path: str,
    *,
    provider_name: str,
    params: dict[str, Any] | None = None,
    accept: str | None = None,
    health: ProviderHealthState | None = None,
    rate_limiter: _OutboundRateLimiter | None = None,
    base: str = "explorer",
) -> httpx.Response:
    """Lichess HTTP via shared client + local RPH spacing.

    ``base``: ``explorer`` → opening explorer host; ``site`` → lichess.org API.
    """
    if rate_limiter is not None:
        await rate_limiter.acquire()
    headers = auth_headers()
    if accept:
        headers["Accept"] = accept
    url = site_url(path) if base == "site" else explorer_url(path)
    started = time.perf_counter()
    try:
        response = await request(
            method,
            url,
            provider=PROVIDER_HTTP_KEY,
            max_retries=settings.LICHESS_HTTP_MAX_RETRIES,
            timeout=build_timeout(
                connect=min(5.0, settings.LICHESS_HTTP_TIMEOUT_SECONDS),
                read=settings.LICHESS_HTTP_TIMEOUT_SECONDS,
            ),
            headers=headers,
            params=params,
        )
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        duration_ms = (time.perf_counter() - started) * 1000.0
        log_provider_request(
            provider=provider_name,
            action=path,
            outcome="transport_error",
            duration_ms=duration_ms,
            status_class="transport",
            error_class=type(exc).__name__,
        )
        logger.warning(
            "lichess_transport_error provider=%s path=%s error=%s",
            provider_name,
            path,
            exc,
        )
        if health is not None:
            _mark_failure(health, str(exc))
        raise ChessProviderUnavailableError(
            f"Lichess transport error: {exc}",
            provider=provider_name,
        ) from exc

    duration_ms = (time.perf_counter() - started) * 1000.0
    if response.status_code >= 400:
        err = map_http_error(provider=provider_name, response=response, action=path)
        status_class = f"{response.status_code // 100}xx"
        outcome = "failure" if response.status_code >= 500 else "client_error"
        log_provider_request(
            provider=provider_name,
            action=path,
            outcome=outcome,
            duration_ms=duration_ms,
            status_class=status_class,
            error_class=err.code,
        )
        logger.warning(
            "lichess_http_error provider=%s path=%s status=%s code=%s retryable=%s",
            provider_name,
            path,
            response.status_code,
            err.code,
            err.retryable,
        )
        if health is not None:
            _mark_failure(health, str(err))
        raise err

    log_provider_request(
        provider=provider_name,
        action=path,
        outcome="success",
        duration_ms=duration_ms,
        status_class=f"{response.status_code // 100}xx",
    )
    if health is not None:
        _mark_success(health)
    return response


def _mark_success(health: ProviderHealthState) -> None:
    health.healthy = True
    health.detail = None
    health.last_success_at = datetime.now(timezone.utc)
    health.consecutive_failures = 0
    health.last_error = None


def _mark_failure(health: ProviderHealthState, message: str) -> None:
    health.healthy = False
    health.detail = message
    health.last_error = message
    health.last_error_at = datetime.now(timezone.utc)
    health.consecutive_failures += 1
