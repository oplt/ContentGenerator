from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis
from fastapi import HTTPException

from backend.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self) -> None:
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )  # type: ignore[no-untyped-call]

        logger.info(f"Redis client created for URL: {settings.REDIS_URL}")
        # Don't test connection here - it will be tested during startup

    async def connect(self) -> None:
        """Initialize Redis connection - call this during app startup"""
        try:
            await self.redis_client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise HTTPException(status_code=500, detail="Redis connection failed") from e

    async def close(self) -> None:
        """Close Redis connection - call this during app shutdown"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = await self.redis_client.get(key)
            if value is None:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            logger.error(f"Error getting key {key} from cache: {e}")
            return None

    async def set(self, key: str, value: Any, expire: int = 300, **kwargs: Any) -> bool:
        """Set value in cache with expiration (default 5 minutes)"""
        try:
            if kwargs:
                result = await self.redis_client.set(key, value, **kwargs)
                return bool(result)
            serialized_value = json.dumps(value)
            result = await self.redis_client.setex(key, expire, serialized_value)
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting key {key} in cache: {e}")
            return False

    async def delete(self, *keys: str) -> bool:
        """Delete key from cache"""
        if not keys:
            return False
        try:
            result = await self.redis_client.delete(*keys)
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting keys {keys} from cache: {e}")
            return False

    async def ping(self) -> bool:
        return bool(await self.redis_client.ping())

    def pipeline(self, *args: Any, **kwargs: Any) -> Any:
        return self.redis_client.pipeline(*args, **kwargs)

    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        result = await self.redis_client.setex(key, seconds, value)
        return bool(result)

    async def flush_all(self) -> bool:
        """Clear all cache"""
        try:
            result = await self.redis_client.flushall()
            return bool(result)
        except Exception as e:
            logger.error(f"Error flushing cache: {e}")
            return False

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple keys from cache"""
        try:
            values = await self.redis_client.mget(keys)
            result = {}
            for key, value in zip(keys, values, strict=True):
                if value is not None:
                    result[key] = json.loads(value)
                else:
                    result[key] = None
            return result
        except Exception as e:
            logger.error(f"Error getting multiple keys from cache: {e}")
            return {}

    async def set_many(self, key_values: dict[str, Any], expire: int = 300) -> int:
        """Set multiple key-value pairs in cache"""
        try:
            pipe = self.redis_client.pipeline()
            for key, value in key_values.items():
                serialized_value = json.dumps(value)
                pipe.setex(key, expire, serialized_value)
            results = await pipe.execute()
            return sum(results)
        except Exception as e:
            logger.error(f"Error setting multiple keys in cache: {e}")
            return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            result = await self.redis_client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Error checking key existence in cache: {e}")
            return False

    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for a key"""
        try:
            result = await self.redis_client.expire(key, seconds)
            return bool(result)
        except Exception as e:
            logger.error(f"Error setting expiration for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """Get time to live for a key"""
        try:
            ttl = await self.redis_client.ttl(key)
            return int(ttl)
        except Exception as e:
            logger.error(f"Error getting TTL for key {key}: {e}")
            return -1


# Create singleton instance
redis_cache = RedisCache()
redis_client = redis_cache.redis_client
