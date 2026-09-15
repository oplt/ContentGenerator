"""
Tenant-safe cache contract (T3.3).

Key format
----------
``cg:{env}:{tenant|global}:{owner}:{identity}``

Rules
-----
* Every retained entry has owner, scoped key, TTL, invalidation path, and metrics.
* Never cache credential plaintext (password hashes, MFA secrets, access tokens).
* Fail-open by default for read-through caches; auth rate-limit keys stay fail-closed
  at the rate_limit module (raw redis), not through this facade.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar, cast
from uuid import UUID

from backend.core.cache import redis_cache
from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics

logger = logging.getLogger(__name__)

T = TypeVar("T")

_NEGATIVE = "__cg_negative__"
_stats: dict[str, int] = {
    "hit": 0,
    "miss": 0,
    "negative_hit": 0,
    "error": 0,
    "set": 0,
    "delete": 0,
    "singleflight_join": 0,
}
_inflight: dict[str, asyncio.Future[Any]] = {}
_inflight_lock = asyncio.Lock()


class CacheFailMode(str, Enum):
    OPEN = "open"  # Redis errors → treat as miss
    CLOSED = "closed"  # Redis errors → raise


@dataclass(frozen=True, slots=True)
class CachePolicy:
    owner: str
    ttl_seconds: int
    negative_ttl_seconds: int = 0
    fail_mode: CacheFailMode = CacheFailMode.OPEN
    # When True, set/get refuse payloads that look like credential material.
    forbid_credentials: bool = True


# Named owners used by migrated call sites.
OWNER_CONTENT_STRATEGY = "content_strategy"
OWNER_IDENTITY = "identity"
OWNER_INGESTION = "ingestion"
OWNER_AUTH_TOKEN = "auth_token"  # short-lived opaque tokens only (not password/MFA secrets)


def get_cache_stats() -> dict[str, int]:
    return dict(_stats)


def reset_cache_stats() -> None:
    for key in _stats:
        _stats[key] = 0


def cache_env() -> str:
    return (settings.APP_ENV or "development").strip().lower() or "development"


def build_cache_key(
    *,
    owner: str,
    identity: str,
    tenant_id: UUID | str | None = None,
    global_scope: bool = False,
) -> str:
    """
    Build ``cg:{env}:{tenant|global}:{owner}:{identity}``.

    ``global_scope=True`` is for non-tenant data (e.g. permission catalog).
    Otherwise ``tenant_id`` is required.
    """
    if not owner or ":" in owner or "/" in owner:
        raise ValueError("owner must be a non-empty token without ':' or '/'")
    if not identity:
        raise ValueError("identity must be non-empty")
    if global_scope:
        scope = "global"
    else:
        if tenant_id is None:
            raise ValueError("tenant_id required unless global_scope=True")
        scope = str(tenant_id)
    # identity may contain ':' for compound ids (e.g. plan:uuid)
    return f"cg:{cache_env()}:{scope}:{owner}:{identity}"


_CREDENTIAL_MARKERS = (
    "password",
    "password_hash",
    "mfa_secret",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "private_key",
)


def _assert_no_credentials(value: Any) -> None:
    if isinstance(value, dict):
        lowered = {str(k).lower() for k in value}
        for marker in _CREDENTIAL_MARKERS:
            if marker in lowered and value.get(marker) not in (None, "", [], {}):
                # Allow empty placeholders; block real material.
                if marker in value and value[marker]:
                    raise ValueError(f"refusing to cache credential field '{marker}'")
        for nested in value.values():
            _assert_no_credentials(nested)
    elif isinstance(value, list):
        for item in value:
            _assert_no_credentials(item)


def orm_column_dict(obj: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize SQLAlchemy mapped columns to a JSON-safe dict."""
    excluded = exclude or set()
    data: dict[str, Any] = {}
    for column in obj.__table__.columns:
        if column.key in excluded:
            continue
        value = getattr(obj, column.key)
        if isinstance(value, UUID):
            data[column.key] = str(value)
        elif hasattr(value, "isoformat"):
            data[column.key] = value.isoformat()
        elif isinstance(value, Enum):
            data[column.key] = value.value
        else:
            data[column.key] = value
    return data


class TenantCache:
    """High-level tenant-safe cache operations over RedisCache."""

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

        if raw is None:
            _stats["miss"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="miss")
            return None

        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            _stats["error"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="error")
            return None

        if isinstance(payload, dict) and payload.get(_NEGATIVE) is True:
            _stats["negative_hit"] += 1
            domain_metrics.record_cache(owner=policy.owner, result="negative_hit")
            return None

        _stats["hit"] += 1
        domain_metrics.record_cache(owner=policy.owner, result="hit")
        return payload

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
                _assert_no_credentials(value)
            except ValueError as exc:
                _stats["error"] += 1
                logger.error("cache_set_blocked key=%s reason=%s", key, exc)
                return False
        ttl = policy.ttl_seconds if ttl_seconds is None else ttl_seconds
        try:
            ok = await self.backend.set(key, value, expire=ttl)
            if ok:
                _stats["set"] += 1
            return ok
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
            {_NEGATIVE: True, "at": time.time()},
            policy=policy,
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
        """
        Best-effort prefix delete for an owner scope.

        Uses SCAN to avoid KEYS on large Redis. Returns deleted count.
        """
        env = cache_env()
        if global_scope:
            scope = "global"
        else:
            if tenant_id is None:
                raise ValueError("tenant_id required unless global_scope=True")
            scope = str(tenant_id)
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
        """
        Read-through with single-flight coalescing for costly misses.

        Optional ``legacy_keys`` enable dual-read during key migrations.
        """
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

        created = False
        async with _inflight_lock:
            existing = _inflight.get(key)
            if existing is not None:
                _stats["singleflight_join"] += 1
                waiter: asyncio.Future[Any] = existing
            else:
                loop = asyncio.get_running_loop()
                waiter = loop.create_future()
                _inflight[key] = waiter
                created = True

        if not created:
            return cast(T | None, await waiter)

        try:
            value = await factory()
            if value is None:
                await self.set_negative(key, policy=policy)
            else:
                await self.set_json(key, value, policy=policy)
            waiter.set_result(value)
            return value
        except Exception as exc:
            if not waiter.done():
                waiter.set_exception(exc)
            raise
        finally:
            async with _inflight_lock:
                _inflight.pop(key, None)


def hydrate_orm(model_cls: type[T], data: dict[str, Any]) -> T:
    """Build a transient ORM instance from a column dict (cache hit path)."""
    obj = model_cls()
    table = getattr(model_cls, "__table__", None)
    if table is None:
        raise TypeError(f"{model_cls} is not a mapped ORM class")
    for column in table.columns:
        if column.key not in data:
            continue
        value = data[column.key]
        if value is None:
            setattr(obj, column.key, None)
            continue
        python_type = getattr(column.type, "python_type", None)
        try:
            if python_type is UUID and not isinstance(value, UUID):
                value = UUID(str(value))
            elif python_type is not None and python_type is not type(value):
                if python_type.__name__ == "datetime" and isinstance(value, str):
                    value = __import__("datetime").datetime.fromisoformat(value)
                elif python_type is bool and isinstance(value, str):
                    value = value.lower() in {"1", "true", "yes"}
        except Exception:
            pass
        setattr(obj, column.key, value)
    return obj


tenant_cache = TenantCache()
