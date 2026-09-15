"""Distributed Redis single-flight locks (Phase 5.3)."""

from __future__ import annotations

import asyncio
import logging
import random
import secrets
from typing import Any

logger = logging.getLogger(__name__)

_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


def lock_key_for(cache_key: str) -> str:
    return f"{cache_key}:sf_lock"


async def acquire_lock(redis: Any, cache_key: str, *, ttl_ms: int) -> str | None:
    token = secrets.token_hex(16)
    try:
        ok = await redis.set(lock_key_for(cache_key), token, nx=True, px=max(ttl_ms, 1))
    except Exception as exc:
        logger.warning("cache_sf_lock_error key=%s error=%s", cache_key, exc)
        return None
    return token if ok else None


async def release_lock(redis: Any, cache_key: str, token: str) -> None:
    try:
        await redis.eval(_RELEASE_LUA, 1, lock_key_for(cache_key), token)
    except Exception as exc:
        logger.warning("cache_sf_unlock_error key=%s error=%s", cache_key, exc)


async def wait_for_fill(*, attempts: int = 8, base_delay: float = 0.025) -> None:
    """Brief backoff with jitter while another worker fills the cache."""
    for attempt in range(max(attempts, 1)):
        delay = base_delay * (2 ** min(attempt, 4))
        delay *= 0.5 + random.random()
        await asyncio.sleep(delay)
