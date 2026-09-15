"""Distributed locks for periodic Celery task overlap protection."""

from __future__ import annotations

from contextlib import asynccontextmanager
from secrets import token_urlsafe
from typing import AsyncIterator

from backend.core.cache import redis_client

_LOCK_PREFIX = "cg:celery:periodic:"
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def periodic_task_lock(name: str, *, ttl_seconds: int) -> AsyncIterator[bool]:
    """Yield whether this task acquired its distributed overlap lock.

    Lock acquisition errors propagate: allowing a periodic task to continue
    without its safety lock could create duplicate side effects.
    """
    key = f"{_LOCK_PREFIX}{name}"
    token = token_urlsafe(24)
    acquired = bool(await redis_client.set(key, token, nx=True, px=ttl_seconds * 1000))
    try:
        yield acquired
    finally:
        if acquired:
            await redis_client.eval(_RELEASE_LOCK, 1, key, token)
