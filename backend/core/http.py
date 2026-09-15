"""Process-wide httpx client, provider semaphores, Retry-After (Phase 4).

One shared AsyncClient; prefer request() so retries/semaphores stay consistent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

_client: httpx.AsyncClient | None = None
_client_lock = asyncio.Lock()
_semaphores: dict[str, asyncio.Semaphore] = {}
_stats: dict[str, int] = {
    "requests": 0,
    "retries": 0,
    "rate_limited": 0,
    "transport_errors": 0,
}


def get_http_stats() -> dict[str, int]:
    return dict(_stats)


def reset_http_stats() -> None:
    for key in _stats:
        _stats[key] = 0


def build_timeout(
    *,
    connect: float | None = None,
    read: float | None = None,
    write: float | None = None,
    pool: float | None = None,
) -> httpx.Timeout:
    return httpx.Timeout(
        connect=connect if connect is not None else settings.HTTP_CONNECT_TIMEOUT_SECONDS,
        read=read if read is not None else settings.HTTP_READ_TIMEOUT_SECONDS,
        write=write if write is not None else settings.HTTP_WRITE_TIMEOUT_SECONDS,
        pool=pool if pool is not None else settings.HTTP_POOL_TIMEOUT_SECONDS,
    )


def build_limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=settings.HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
    )


async def get_http_client() -> httpx.AsyncClient:
    """Return the process-scoped AsyncClient, creating it lazily."""
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                timeout=build_timeout(),
                limits=build_limits(),
                follow_redirects=True,
            )
            logger.info(
                "http_client_started max_connections=%s keepalive=%s",
                settings.HTTP_MAX_CONNECTIONS,
                settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            )
        return _client


async def close_http_client() -> None:
    """Close and clear the process-scoped client (API/worker shutdown)."""
    global _client
    async with _client_lock:
        if _client is not None and not _client.is_closed:
            await _client.aclose()
            logger.info("http_client_closed")
        _client = None


@asynccontextmanager
async def shared_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """
    Drop-in for ``async with httpx.AsyncClient(...)`` that reuses the process client.

    Does not close the client on exit — lifecycle owns shutdown.
    Prefer ``request()`` for production outbound calls.
    """
    yield await get_http_client()


def provider_limit(provider: str) -> int:
    """Max in-flight requests for a provider key."""
    normalized = provider.strip().lower()
    overrides = {
        "github": settings.HTTP_PROVIDER_GITHUB_CONCURRENCY,
        "analytics": settings.HTTP_PROVIDER_ANALYTICS_CONCURRENCY,
        "x": settings.HTTP_PROVIDER_X_CONCURRENCY,
        "llm": settings.HTTP_PROVIDER_LLM_CONCURRENCY,
        "ingestion": settings.HTTP_PROVIDER_INGESTION_CONCURRENCY,
        "publishing": settings.HTTP_PROVIDER_PUBLISHING_CONCURRENCY,
        "image": settings.HTTP_PROVIDER_IMAGE_CONCURRENCY,
        "tts": settings.HTTP_PROVIDER_TTS_CONCURRENCY,
        "approvals": settings.HTTP_PROVIDER_LLM_CONCURRENCY,
    }
    return overrides.get(normalized, settings.HTTP_PROVIDER_MAX_CONCURRENCY)


def provider_semaphore(provider: str) -> asyncio.Semaphore:
    key = provider.strip().lower() or "default"
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(provider_limit(key))
    return _semaphores[key]


def parse_retry_after_seconds(
    response: httpx.Response,
    *,
    default: float = 1.0,
    max_seconds: float | None = None,
) -> float:
    """Parse Retry-After (delta-seconds or HTTP-date) into a clamped UTC-relative delay."""
    clamp = settings.HTTP_RETRY_AFTER_MAX_SECONDS if max_seconds is None else max_seconds

    def _clamp(value: float) -> float:
        return min(max(value, 0.0), clamp)

    raw = response.headers.get("Retry-After")
    if not raw:
        return _clamp(default)
    text = raw.strip()
    try:
        return _clamp(float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        else:
            when = when.astimezone(timezone.utc)
        return _clamp((when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, IndexError, OverflowError):
        return _clamp(default)


async def sleep_retry_after(
    response: httpx.Response,
    *,
    default: float = 1.0,
    provider: str = "default",
) -> None:
    delay = parse_retry_after_seconds(response, default=default)
    _stats["rate_limited"] += 1
    domain_metrics.record_http_429(provider=provider)
    domain_metrics.record_provider_retry(provider=provider, reason="rate_limited")
    await asyncio.sleep(delay)


async def request(
    method: str,
    url: str,
    *,
    provider: str = "default",
    max_retries: int | None = None,
    timeout: httpx.Timeout | float | None = None,
    **kwargs: object,
) -> httpx.Response:
    """
    Shared-client request with provider semaphore + Retry-After / transport retries.

    Semaphore covers a single network attempt only; backoff sleeps run outside the permit.
    Does not raise on 4xx/5xx (caller uses ``raise_for_status``).
    """
    client = await get_http_client()
    try:
        import structlog

        correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")
    except Exception:
        correlation_id = None
    if correlation_id and "X-Correlation-ID" not in (kwargs.get("headers") or {}):
        headers = dict(kwargs.get("headers") or {})
        headers["X-Correlation-ID"] = str(correlation_id)
        kwargs["headers"] = headers
    retries = settings.HTTP_MAX_RETRIES if max_retries is None else max_retries
    sem = provider_semaphore(provider)
    last_error: BaseException | None = None
    started = time.perf_counter()
    outcome = "success"
    status_class = "none"

    for attempt in range(retries + 1):
        _stats["requests"] += 1
        try:
            wait_started = time.perf_counter()
            await sem.acquire()
            domain_metrics.record_semaphore_wait(
                provider=provider,
                duration_ms=(time.perf_counter() - wait_started) * 1000.0,
            )
            try:
                response = await client.request(
                    method,
                    url,
                    timeout=timeout if timeout is not None else build_timeout(),
                    **kwargs,  # type: ignore[arg-type]
                )
            finally:
                sem.release()
            if response.status_code == 429:
                # Count once here when not retrying; sleep_retry_after also counts.
                if attempt >= retries:
                    domain_metrics.record_http_429(provider=provider)
                if attempt < retries:
                    _stats["retries"] += 1
                    await sleep_retry_after(response, provider=provider)
                    continue
            status_class = f"{response.status_code // 100}xx"
            if response.status_code >= 500:
                outcome = "failure"
            elif response.status_code >= 400:
                outcome = "client_error"
            domain_metrics.record_provider_request(
                provider=provider,
                outcome=outcome,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                status_class=status_class,
            )
            return response
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            _stats["transport_errors"] += 1
            last_error = exc
            if attempt >= retries:
                domain_metrics.record_provider_request(
                    provider=provider,
                    outcome="transport_error",
                    duration_ms=(time.perf_counter() - started) * 1000.0,
                    status_class="transport",
                )
                raise
            _stats["retries"] += 1
            domain_metrics.record_provider_retry(provider=provider, reason="transport")
            await asyncio.sleep(min(2**attempt, 8))

    assert last_error is not None
    raise last_error


async def map_concurrent(
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    limit: int,
    return_exceptions: bool = True,
) -> list[R | BaseException]:
    """
    Run ``worker`` over ``items`` with bounded concurrency.

    Preserves input order. When ``return_exceptions`` is True, ordinary failures become
    exception objects in-place so successful siblings are kept. Cancellation and other
    ``BaseException`` types always propagate.
    """
    if not items:
        return []
    if limit < 1:
        raise ValueError("limit must be >= 1")

    sem = asyncio.Semaphore(limit)
    results: list[R | BaseException | None] = [None] * len(items)

    async def _run(index: int, item: T) -> None:
        async with sem:
            try:
                results[index] = await worker(item)
            except Exception as exc:
                if return_exceptions:
                    results[index] = exc
                else:
                    raise

    async with asyncio.TaskGroup() as group:
        for index, item in enumerate(items):
            group.create_task(_run(index, item))

    return [item if item is not None else RuntimeError("missing result") for item in results]
