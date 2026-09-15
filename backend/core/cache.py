"""
Redis client facade with a shared value codec (Phase 5).

Never use FLUSHALL against the shared Redis used by Celery + app cache.
Use ``flush_namespace`` (SCAN + DELETE) for ``cg:{env}:*`` keys only.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import redis.asyncio as redis
from fastapi import HTTPException

from backend.core.cache_codec import CODEC_MISS, decode, encode
from backend.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self) -> None:
        url = (settings.REDIS_CACHE_URL or settings.REDIS_URL).strip() or settings.REDIS_URL
        self.redis_client = redis.from_url(
            url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )  # type: ignore[no-untyped-call]
        logger.info("Redis client created for URL: %s", url)

    async def connect(self) -> None:
        try:
            await self.redis_client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            raise HTTPException(status_code=500, detail="Redis connection failed") from e

    async def close(self) -> None:
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[Any]:
        try:
            value = await self.redis_client.get(key)
            decoded = decode(value)
            if decoded is CODEC_MISS:
                return None
            return decoded
        except Exception as e:
            logger.error("Error getting key %s from cache: %s", key, e)
            return None

    async def set(self, key: str, value: Any, expire: int = 300, **kwargs: Any) -> bool:
        try:
            if kwargs:
                # Low-level SET options (NX/PX locks) — caller supplies already-encoded value.
                result = await self.redis_client.set(key, value, **kwargs)
                return bool(result)
            result = await self.redis_client.setex(key, expire, encode(value))
            return bool(result)
        except Exception as e:
            logger.error("Error setting key %s in cache: %s", key, e)
            return False

    async def delete(self, *keys: str) -> bool:
        if not keys:
            return False
        try:
            result = await self.redis_client.delete(*keys)
            return bool(result)
        except Exception as e:
            logger.error("Error deleting keys %s from cache: %s", keys, e)
            return False

    async def ping(self) -> bool:
        return bool(await self.redis_client.ping())

    def pipeline(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis_client.pipeline(*args, **kwargs)

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        try:
            result = await self.redis_client.setex(key, seconds, encode(value))
            return bool(result)
        except Exception as e:
            logger.error("Error setex key %s in cache: %s", key, e)
            return False

    async def flush_namespace(self, match: str | None = None) -> int:
        """
        Delete keys matching a namespace prefix via SCAN.

        Default match is ``cg:{APP_ENV}:*`` — never FLUSHALL.
        """
        from backend.core.tenant_cache import cache_env

        pattern = match or f"cg:{cache_env()}:*"
        deleted = 0
        try:
            async for key in self.redis_client.scan_iter(match=pattern, count=200):
                await self.redis_client.delete(key)
                deleted += 1
        except Exception as e:
            logger.error("Error flushing namespace %s: %s", pattern, e)
            return deleted
        return deleted

    async def flush_all(self) -> bool:
        """Deprecated. Namespace-scoped delete only — never FLUSHALL."""
        logger.error("flush_all_refused use flush_namespace instead")
        deleted = await self.flush_namespace()
        return deleted >= 0

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        try:
            values = await self.redis_client.mget(keys)
            result: dict[str, Any] = {}
            for key, value in zip(keys, values, strict=True):
                decoded = decode(value)
                result[key] = None if decoded is CODEC_MISS else decoded
            return result
        except Exception as e:
            logger.error("Error getting multiple keys from cache: %s", e)
            return {}

    async def set_many(self, key_values: dict[str, Any], expire: int = 300) -> int:
        try:
            pipe = self.redis_client.pipeline()
            for key, value in key_values.items():
                pipe.setex(key, expire, encode(value))
            results = await pipe.execute()
            return sum(1 for item in results if item)
        except Exception as e:
            logger.error("Error setting multiple keys in cache: %s", e)
            return 0

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.error("Error checking key existence in cache: %s", e)
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        try:
            return bool(await self.redis_client.expire(key, seconds))
        except Exception as e:
            logger.error("Error setting expiration for key %s: %s", key, e)
            return False

    async def ttl(self, key: str) -> int:
        try:
            return int(await self.redis_client.ttl(key))
        except Exception as e:
            logger.error("Error getting TTL for key %s: %s", key, e)
            return -1


redis_cache = RedisCache()
redis_client = redis_cache.redis_client
