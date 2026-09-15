"""
Lifecycle-owned HTTP client, provider concurrency budgets, and Retry-After (T3.2).

Ownership
---------
* One process-wide ``httpx.AsyncClient`` (API lifespan / Celery worker process).
* Callers must not create short-lived clients for outbound provider I/O.
* ``close_http_client()`` on shutdown — never leave sockets open across forks
  without recreating the client in the child.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
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
    }
    return overrides.get(normalized, settings.HTTP_PROVIDER_MAX_CONCURRENCY)


def provider_semaphore(provider: str) -> asyncio.Semaphore:
    key = provider.strip().lower() or "default"
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(provider_limit(key))
    return _semaphores[key]


def parse_retry_after_seconds(response: httpx.Response, *, default: float = 1.0) -> float:
    """Parse Retry-After header (seconds or HTTP-date) into a sleep duration."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return default
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return default


async def sleep_retry_after(
    response: httpx.Response,
    *,
    default: float = 1.0,
    provider: str = "default",
) -> None:
    delay = parse_retry_after_seconds(response, default=default)
    _stats["rate_limited"] += 1
    domain_metrics.record_provider_retry(provider=provider, reason="rate_limited")
    await asyncio.sleep(min(delay, 60.0))


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

    Does not raise on 4xx/5xx (caller uses ``raise_for_status``). Retries 429 and
    transport/timeouts up to ``max_retries``.
    """
    client = await get_http_client()
    retries = settings.HTTP_MAX_RETRIES if max_retries is None else max_retries
    sem = provider_semaphore(provider)
    last_error: BaseException | None = None
    started = time.perf_counter()
    outcome = "success"
    status_class = "none"

    async with sem:
        for attempt in range(retries + 1):
            _stats["requests"] += 1
            try:
                response = await client.request(
                    method,
                    url,
                    timeout=timeout if timeout is not None else build_timeout(),
                    **kwargs,  # type: ignore[arg-type]
                )
                if response.status_code == 429 and attempt < retries:
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

    Preserves input order. When ``return_exceptions`` is True, failures become
    exception objects in-place so successful siblings are kept (partial results).
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
            except BaseException as exc:
                if return_exceptions:
                    results[index] = exc
                else:
                    raise

    async with asyncio.TaskGroup() as group:
        for index, item in enumerate(items):
            group.create_task(_run(index, item))

    return [item if item is not None else RuntimeError("missing result") for item in results]
