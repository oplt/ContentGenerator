"""Phase 4: HTTP policy, Retry-After, semaphore residency, cancellation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.etree import ElementTree

import httpx
import respx

from backend.core import http as http_mod
from backend.core.config import settings
from backend.core.http import (
    close_http_client,
    map_concurrent,
    parse_retry_after_seconds,
    provider_semaphore,
    request,
    reset_http_stats,
)
from backend.modules.source_ingestion.sitemap_walk import walk_sitemap_urls


def test_parse_retry_after_http_date_and_clamp() -> None:
    when = datetime.now(timezone.utc) + timedelta(seconds=12)
    response = httpx.Response(429, headers={"Retry-After": format_datetime(when)})
    delay = parse_retry_after_seconds(response)
    assert 0.0 <= delay <= settings.HTTP_RETRY_AFTER_MAX_SECONDS
    assert delay == 12.0 or abs(delay - 12.0) < 2.0

    huge = httpx.Response(429, headers={"Retry-After": "99999"})
    assert parse_retry_after_seconds(huge) == settings.HTTP_RETRY_AFTER_MAX_SECONDS

    decimal = httpx.Response(429, headers={"Retry-After": "1.5"})
    assert parse_retry_after_seconds(decimal) == 1.5


def test_map_concurrent_propagates_cancellation() -> None:
    async def _run() -> None:
        async def worker(_: int) -> int:
            await asyncio.sleep(0.05)
            return 1

        task = asyncio.create_task(map_concurrent([1, 2, 3], worker, limit=2, return_exceptions=True))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
            raise AssertionError("expected CancelledError")
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


@respx.mock
def test_request_releases_semaphore_during_retry_sleep(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def _run() -> None:
        await close_http_client()
        reset_http_stats()
        http_mod._semaphores.clear()
        monkeypatch.setattr(settings, "HTTP_PROVIDER_MAX_CONCURRENCY", 1)
        monkeypatch.setattr(settings, "HTTP_MAX_RETRIES", 2)

        seen_available: list[int] = []
        real_sleep = asyncio.sleep

        async def _spy_sleep(delay: float) -> None:
            sem = provider_semaphore("phase4test")
            seen_available.append(sem._value)
            await real_sleep(0)

        monkeypatch.setattr(http_mod.asyncio, "sleep", _spy_sleep)

        respx.get("https://example.test/phase4").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "1"}),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        response = await request("GET", "https://example.test/phase4", provider="phase4test", max_retries=2)
        assert response.status_code == 200
        assert seen_available
        assert all(value >= 1 for value in seen_available)

        await close_http_client()
        http_mod._semaphores.clear()

    asyncio.run(_run())


def test_sitemap_walk_respects_limits_and_order() -> None:
    async def _run() -> None:
        pages = {
            "https://example.test/sitemap.xml": """<?xml version="1.0"?>
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://example.test/a.xml</loc></sitemap>
              <sitemap><loc>https://example.test/b.xml</loc></sitemap>
            </sitemapindex>
            """,
            "https://example.test/a.xml": """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.test/a1</loc></url>
              <url><loc>https://example.test/a2</loc></url>
            </urlset>
            """,
            "https://example.test/b.xml": """<?xml version="1.0"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.test/b1</loc></url>
            </urlset>
            """,
        }
        peak = 0
        current = 0
        lock = asyncio.Lock()

        async def fetch_text(url: str) -> str:
            nonlocal peak, current
            async with lock:
                current += 1
                peak = max(peak, current)
            await asyncio.sleep(0.01)
            async with lock:
                current -= 1
            return pages[url]

        urls = await walk_sitemap_urls(
            "https://example.test/sitemap.xml",
            fetch_text=fetch_text,
            parse_xml=ElementTree.fromstring,
            max_depth=2,
            max_urls=10,
            change_window_hours=72,
            timeout_seconds=5.0,
            global_limit=2,
            per_origin_limit=2,
        )
        assert urls == [
            "https://example.test/a1",
            "https://example.test/a2",
            "https://example.test/b1",
        ]
        assert peak <= 2

    asyncio.run(_run())
