"""Tests for shared HTTP client, concurrency bounds, and Retry-After (T3.2)."""

from __future__ import annotations

import asyncio

import httpx
import respx

from backend.core.http import (
    close_http_client,
    get_http_client,
    get_http_stats,
    map_concurrent,
    parse_retry_after_seconds,
    provider_limit,
    request,
    reset_http_stats,
    shared_http_client,
)


def test_provider_limits_are_positive_and_scoped() -> None:
    assert provider_limit("github") >= 1
    assert provider_limit("analytics") >= 1
    assert provider_limit("unknown-provider") >= 1


def test_parse_retry_after_seconds() -> None:
    response = httpx.Response(429, headers={"Retry-After": "2"})
    assert parse_retry_after_seconds(response) == 2.0
    assert parse_retry_after_seconds(httpx.Response(429), default=1.5) == 1.5


def test_map_concurrent_preserves_order_and_partial_failures() -> None:
    async def _run() -> None:
        async def worker(n: int) -> int:
            if n == 2:
                raise RuntimeError("boom")
            await asyncio.sleep(0.01 * (3 - n))
            return n * 10

        outcomes = await map_concurrent([1, 2, 3], worker, limit=2, return_exceptions=True)
        assert outcomes[0] == 10
        assert isinstance(outcomes[1], RuntimeError)
        assert outcomes[2] == 30

    asyncio.run(_run())


def test_map_concurrent_enforces_limit() -> None:
    async def _run() -> None:
        current = 0
        peak = 0
        lock = asyncio.Lock()

        async def worker(_: int) -> int:
            nonlocal current, peak
            async with lock:
                current += 1
                peak = max(peak, current)
            await asyncio.sleep(0.02)
            async with lock:
                current -= 1
            return 1

        await map_concurrent(list(range(8)), worker, limit=3, return_exceptions=False)
        assert peak <= 3

    asyncio.run(_run())


@respx.mock
def test_shared_client_reuses_connection_and_retries_429() -> None:
    async def _run() -> None:
        await close_http_client()
        reset_http_stats()
        route = respx.get("https://example.test/item").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        first = await get_http_client()
        second = await get_http_client()
        assert first is second

        response = await request("GET", "https://example.test/item", provider="analytics", max_retries=2)
        assert response.status_code == 200
        assert route.call_count == 2
        stats = get_http_stats()
        assert stats["rate_limited"] >= 1
        assert stats["retries"] >= 1

        async with shared_http_client() as client:
            assert client is first

        await close_http_client()

    asyncio.run(_run())
