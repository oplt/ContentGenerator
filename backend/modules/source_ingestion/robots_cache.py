"""Origin-scoped robots.txt cache (Phase 5.6)."""

from __future__ import annotations

import logging
import urllib.robotparser
from urllib.parse import urlparse

from backend.core.config import settings
from backend.core.http import request
from backend.core.tenant_cache import (
    OWNER_ROBOTS,
    CachePolicy,
    build_cache_key,
    tenant_cache,
)

logger = logging.getLogger(__name__)

_ROBOTS_POLICY = CachePolicy(
    owner=OWNER_ROBOTS,
    ttl_seconds=settings.CACHE_ROBOTS_TTL_SECONDS,
    negative_ttl_seconds=300,
    ttl_jitter_seconds=60,
    singleflight=True,
)


def _origin_key(robots_url: str) -> str:
    parsed = urlparse(robots_url)
    return f"{parsed.scheme}://{parsed.netloc}".lower()


async def fetch_robots_text(robots_url: str) -> str | None:
    key = build_cache_key(
        owner=OWNER_ROBOTS,
        identity=_origin_key(robots_url),
        global_scope=True,
    )

    async def _load() -> str | None:
        try:
            response = await request(
                "GET",
                robots_url,
                provider="ingestion",
                headers={"User-Agent": settings.APP_NAME},
            )
            response.raise_for_status()
            return response.text
        except Exception as exc:
            logger.info("robots_fetch_failed origin=%s error=%s", _origin_key(robots_url), type(exc).__name__)
            return None

    return await tenant_cache.get_or_set(key, policy=_ROBOTS_POLICY, factory=_load)


async def robots_allowed(url: str, *, user_agent: str, respected: bool) -> bool:
    if not respected:
        return True
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    text = await fetch_robots_text(robots_url)
    if text is None:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(text.splitlines())
    return parser.can_fetch(user_agent, url)
