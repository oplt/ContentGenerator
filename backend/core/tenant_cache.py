"""
Tenant-safe cache contract (T3.3 / Phase 5).

Key format: ``cg:{env}:{tenant|global}:{owner}:{identity}``
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar, cast
from uuid import UUID

from backend.core import cache_singleflight as sf
from backend.core.cache import redis_cache
from backend.core.cache_codec import CODEC_MISS, decode, encode
from backend.core.cache_support import (
    assert_no_credentials,
    effective_ttl,
    hydrate_orm as hydrate_orm,
    is_negative_payload,
    negative_payload,
    orm_column_dict as orm_column_dict,
    unwrap_payload,
    wrap_payload,
)
from backend.core.cache_keys import (
    OWNER_AUTH_TOKEN as OWNER_AUTH_TOKEN,
    OWNER_CONTENT_STRATEGY as OWNER_CONTENT_STRATEGY,
    OWNER_IDENTITY as OWNER_IDENTITY,
    OWNER_INGESTION as OWNER_INGESTION,
    OWNER_OAUTH as OWNER_OAUTH,
    OWNER_ROBOTS as OWNER_ROBOTS,
    build_cache_key as build_cache_key,
    cache_env,
)
from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics

logger = logging.getLogger(__name__)

T = TypeVar("T")

_stats: dict[str, int] = {
    "hit": 0,
    "miss": 0,
    "negative_hit": 0,
    "error": 0,
    "set": 0,
    "delete": 0,
    "singleflight_join": 0,
    "stampede_lock_wait": 0,
    "stale_served": 0,
    "fill_duration_ms_total": 0,
}
_inflight: dict[str, asyncio.Future[Any]] = {}
_inflight_lock = asyncio.Lock()


class CacheFailMode(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class CachePolicy:
    owner: str
    ttl_seconds: int
    negative_ttl_seconds: int = 0
    fail_mode: CacheFailMode = CacheFailMode.OPEN
    forbid_credentials: bool = True
    singleflight: bool = True
    swr_seconds: int = 0
    ttl_jitter_seconds: int = 0


def get_cache_stats() -> dict[str, int]:
    return dict(_stats)


def reset_cache_stats() -> None:
    for key in _stats:
        _stats[key] = 0


class TenantCache:
    def __init__(self, backend: Any = None) -> None:
        self.backend = backend or redis_cache

    async def get_json(self, key: str, *, policy: CachePolicy) -> Any | None:
        try:
            raw = await self.backend.redis_client.get(key)
        except Exception as exc:
            _stats["error"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="error")
            logger.warning("cache_get_error key=%s error=%s", key, exc)
            if policy.fail_mode is CacheFailMode.CLOSED:
                raise
            return None

        decoded = decode(raw)
        if decoded is CODEC_MISS:
            _stats["miss"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="miss")
            return None

        if is_negative_payload(decoded):
            _stats["negative_hit"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="negative_hit")
            return None

        value, stale = unwrap_payload(decoded)
        if stale:
            _stats["stale_served"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="stale_served")
        else:
            _stats["hit"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="hit")
        return value

    async def set_json(
        self,
        key: str,
        value: Any,
        *,
        policy: CachePolicy,
        ttl_seconds: int | None = None,
    ) -> bool:
        if policy.forbid_credentials:
            try:
                assert_no_credentials(value)
            except ValueError as exc:
                _stats["error"] += 1
                logger.error("cache_set_blocked key=%s reason=%s", key, exc)
                return False
        soft_ttl = effective_ttl(
            ttl_seconds=policy.ttl_seconds if ttl_seconds is None else ttl_seconds,
            jitter_seconds=policy.ttl_jitter_seconds,
        )
        hard_ttl = soft_ttl + max(policy.swr_seconds, 0)
        payload = wrap_payload(value, soft_ttl=soft_ttl, swr_seconds=policy.swr_seconds)
        try:
            ok = await self.backend.redis_client.setex(key, hard_ttl, encode(payload))
            if ok:
                _stats["set"] += 1
            return bool(ok)
        except Exception as exc:
            _stats["error"] += 1
            logger.warning("cache_set_error key=%s error=%s", key, exc)
            if policy.fail_mode is CacheFailMode.CLOSED:
                raise
            return False

    async def set_negative(self, key: str, *, policy: CachePolicy) -> bool:
        if policy.negative_ttl_seconds <= 0:
            return False
        return await self.set_json(
            key,
            negative_payload(),
            policy=CachePolicy(
                owner=policy.owner,
                ttl_seconds=policy.negative_ttl_seconds,
                fail_mode=policy.fail_mode,
                forbid_credentials=False,
                singleflight=False,
            ),
            ttl_seconds=policy.negative_ttl_seconds,
        )

    async def delete(self, *keys: str) -> bool:
        if not keys:
            return False
        try:
            ok = await self.backend.delete(*keys)
            if ok:
                _stats["delete"] += 1
            return ok
        except Exception as exc:
            _stats["error"] += 1
            logger.warning("cache_delete_error keys=%s error=%s", keys, exc)
            return False

    async def invalidate_owner(
        self,
        *,
        owner: str,
        tenant_id: UUID | str | None = None,
        global_scope: bool = False,
    ) -> int:
        env = cache_env()
        scope = "global" if global_scope else str(tenant_id)
        if not global_scope and tenant_id is None:
            raise ValueError("tenant_id required unless global_scope=True")
        match = f"cg:{env}:{scope}:{owner}:*"
        deleted = 0
        try:
            async for key in self.backend.redis_client.scan_iter(match=match, count=100):
                await self.backend.redis_client.delete(key)
                deleted += 1
                _stats["delete"] += 1
        except Exception as exc:
            _stats["error"] += 1
            logger.warning("cache_invalidate_error match=%s error=%s", match, exc)
        return deleted

    async def get_or_set(
        self,
        key: str,
        *,
        policy: CachePolicy,
        factory: Callable[[], Awaitable[T | None]],
        legacy_keys: list[str] | None = None,
    ) -> T | None:
        cached = await self.get_json(key, policy=policy)
        if cached is not None:
            return cast(T, cached)

        if legacy_keys:
            for legacy in legacy_keys:
                legacy_val = await self.get_json(legacy, policy=policy)
                if legacy_val is not None:
                    await self.set_json(key, legacy_val, policy=policy)
                    await self.delete(legacy)
                    return cast(T, legacy_val)

        if not policy.singleflight:
            return await self._fill(key, policy=policy, factory=factory)

        created = False
        async with _inflight_lock:
            existing = _inflight.get(key)
            if existing is not None:
                _stats["singleflight_join"] += 1
                waiter: asyncio.Future[Any] = existing
            else:
                waiter = asyncio.get_running_loop().create_future()
                _inflight[key] = waiter
                created = True

        if not created:
            return cast(T | None, await waiter)

        try:
            value = await self._distributed_fill(key, policy=policy, factory=factory)
            waiter.set_result(value)
            return value
        except Exception as exc:
            if not waiter.done():
                waiter.set_exception(exc)
            raise
        finally:
            async with _inflight_lock:
                _inflight.pop(key, None)

    async def _fill(
        self,
        key: str,
        *,
        policy: CachePolicy,
        factory: Callable[[], Awaitable[T | None]],
    ) -> T | None:
        started = time.perf_counter()
        value = await factory()
        _stats["fill_duration_ms_total"] += int((time.perf_counter() - started) * 1000)
        if value is None:
            await self.set_negative(key, policy=policy)
        else:
            await self.set_json(key, value, policy=policy)
        return value

    async def _distributed_fill(
        self,
        key: str,
        *,
        policy: CachePolicy,
        factory: Callable[[], Awaitable[T | None]],
    ) -> T | None:
        lock_ms = int(getattr(settings, "CACHE_SINGLEFLIGHT_LOCK_MS", 15_000))
        token = await sf.acquire_lock(self.backend.redis_client, key, ttl_ms=lock_ms)
        if token:
            try:
                return await self._fill(key, policy=policy, factory=factory)
            finally:
                await sf.release_lock(self.backend.redis_client, key, token)

        _stats["stampede_lock_wait"] += 1
        domain_metrics.record_cache(owner=policy.owner, result="stampede_lock_wait")
        await sf.wait_for_fill()
        cached = await self.get_json(key, policy=policy)
        if cached is not None:
            return cast(T, cached)
        return await self._fill(key, policy=policy, factory=factory)


tenant_cache = TenantCache()
