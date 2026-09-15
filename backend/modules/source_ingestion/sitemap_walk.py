"""Bounded concurrent sitemap traversal (Phase 4.3)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree

from backend.core.config import settings
from backend.core.http import map_concurrent

logger = logging.getLogger(__name__)

FetchText = Callable[[str], Awaitable[str]]
ParseXml = Callable[[str], ElementTree.Element]


def extract_sitemap_urls(
    root: ElementTree.Element,
) -> tuple[list[str], list[tuple[str, datetime | None]]]:
    namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sitemap_nodes = [item.text for item in root.findall(".//ns:sitemap/ns:loc", namespace) if item.text]
    url_nodes: list[tuple[str, datetime | None]] = []
    for url_node in root.findall(".//ns:url", namespace):
        loc = url_node.findtext("ns:loc", namespaces=namespace)
        lastmod_raw = url_node.findtext("ns:lastmod", namespaces=namespace)
        lastmod = None
        if lastmod_raw:
            try:
                parsed = datetime.fromisoformat(lastmod_raw.replace("Z", "+00:00"))
                lastmod = parsed.astimezone(timezone.utc)
            except Exception:
                lastmod = None
        if loc:
            url_nodes.append((loc, lastmod))
    return sitemap_nodes, url_nodes


async def walk_sitemap_urls(
    root_url: str,
    *,
    fetch_text: FetchText,
    parse_xml: ParseXml,
    max_depth: int,
    max_urls: int,
    change_window_hours: int,
    timeout_seconds: float,
    global_limit: int | None = None,
    per_origin_limit: int | None = None,
) -> list[str]:
    """
    BFS sitemap walk with global + per-origin concurrency, depth/URL caps, and timeout.

    Cancellation propagates via TaskGroup inside ``map_concurrent``.
    """
    global_cap = global_limit if global_limit is not None else settings.HTTP_SITEMAP_GLOBAL_CONCURRENCY
    origin_cap = (
        per_origin_limit if per_origin_limit is not None else settings.HTTP_SITEMAP_PER_ORIGIN_CONCURRENCY
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=change_window_hours)
    origin_sems: dict[str, asyncio.Semaphore] = {}

    def _origin_sem(url: str) -> asyncio.Semaphore:
        origin = urlparse(url).netloc.lower() or "default"
        if origin not in origin_sems:
            origin_sems[origin] = asyncio.Semaphore(origin_cap)
        return origin_sems[origin]

    async def _walk() -> list[str]:
        collected: list[str] = []
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(root_url, 0)]

        while queue and len(collected) < max_urls:
            batch = [(url, depth) for url, depth in queue if url not in visited and depth <= max_depth]
            for url, _depth in batch:
                visited.add(url)
            queue = []
            if not batch:
                break

            async def _process(item: tuple[str, int]) -> tuple[list[str], list[tuple[str, int]]]:
                url, depth = item
                async with _origin_sem(url):
                    xml_text = await fetch_text(url)
                root = await asyncio.to_thread(parse_xml, xml_text)
                nested, url_nodes = extract_sitemap_urls(root)
                page_urls = [
                    loc for loc, lastmod in url_nodes if not lastmod or lastmod >= cutoff
                ]
                children = [
                    (nested_url, depth + 1)
                    for nested_url in nested
                    if nested_url not in visited and depth + 1 <= max_depth
                ]
                return page_urls, children

            outcomes = await map_concurrent(
                batch,
                _process,
                limit=max(1, global_cap),
                return_exceptions=True,
            )
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    logger.warning("sitemap_node_failed error=%s", outcome)
                    continue
                page_urls, children = outcome
                for loc in page_urls:
                    if len(collected) >= max_urls:
                        break
                    collected.append(loc)
                if len(collected) >= max_urls:
                    break
                queue.extend(children)
        return collected

    try:
        return await asyncio.wait_for(_walk(), timeout=timeout_seconds)
    except TimeoutError:
        logger.warning("sitemap_walk_timeout root=%s timeout=%s", root_url, timeout_seconds)
        raise
