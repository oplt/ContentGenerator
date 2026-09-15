"""Tests for tenant-safe cache keys, policies, and single-flight (T3.3)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from backend.core.tenant_cache import (
    OWNER_CONTENT_STRATEGY,
    CachePolicy,
    TenantCache,
    build_cache_key,
    get_cache_stats,
    reset_cache_stats,
    tenant_cache,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, seconds: int, value: str):
        self.store[key] = value
        return True

    async def set(self, key: str, value: str, **kwargs):
        self.store[key] = value
        return True

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                deleted += 1
        return deleted

    async def scan_iter(self, match: str = "*", count: int = 100):
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


class _FakeBackend:
    def __init__(self) -> None:
        self.redis_client = _FakeRedis()

    async def set(self, key: str, value, expire: int = 300, **kwargs):
        import json

        await self.redis_client.setex(key, expire, json.dumps(value))
        return True

    async def delete(self, *keys: str):
        return bool(await self.redis_client.delete(*keys))


def test_build_cache_key_requires_tenant_unless_global() -> None:
    tenant = uuid4()
    key = build_cache_key(
        owner=OWNER_CONTENT_STRATEGY,
        tenant_id=tenant,
        identity="brand:default",
    )
    assert key.startswith("cg:")
    assert str(tenant) in key
    assert OWNER_CONTENT_STRATEGY in key

    with pytest.raises(ValueError):
        build_cache_key(owner="x", identity="y")

    global_key = build_cache_key(owner="identity", identity="permissions:all", global_scope=True)
    assert ":global:" in global_key


def test_refuses_credential_payloads() -> None:
    async def _run() -> None:
        backend = _FakeBackend()
        cache = TenantCache(backend=backend)
        key = build_cache_key(owner="identity", tenant_id=uuid4(), identity="bad")
        policy = CachePolicy(owner="identity", ttl_seconds=60)
        ok = await cache.set_json(key, {"email": "a@b.c", "password_hash": "secret"}, policy=policy)
        assert ok is False
        assert key not in backend.redis_client.store

    asyncio.run(_run())


def test_cross_tenant_keys_do_not_collide() -> None:
    a = uuid4()
    b = uuid4()
    key_a = build_cache_key(owner="content_strategy", tenant_id=a, identity="plan:1")
    key_b = build_cache_key(owner="content_strategy", tenant_id=b, identity="plan:1")
    assert key_a != key_b


def test_singleflight_coalesces_misses() -> None:
    async def _run() -> None:
        reset_cache_stats()
        backend = _FakeBackend()
        cache = TenantCache(backend=backend)
        key = build_cache_key(owner="content_strategy", tenant_id=uuid4(), identity="stampede")
        policy = CachePolicy(owner="content_strategy", ttl_seconds=60)
        calls = 0

        async def factory():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return {"n": calls}

        results = await asyncio.gather(
            cache.get_or_set(key, policy=policy, factory=factory),
            cache.get_or_set(key, policy=policy, factory=factory),
            cache.get_or_set(key, policy=policy, factory=factory),
        )
        assert calls == 1
        assert results == [{"n": 1}, {"n": 1}, {"n": 1}]
        stats = get_cache_stats()
        assert stats["singleflight_join"] >= 1
        assert stats["set"] >= 1

    asyncio.run(_run())


def test_invalidate_owner_prefix() -> None:
    async def _run() -> None:
        backend = _FakeBackend()
        cache = TenantCache(backend=backend)
        tenant = uuid4()
        policy = CachePolicy(owner="content_strategy", ttl_seconds=60)
        k1 = build_cache_key(owner="content_strategy", tenant_id=tenant, identity="a")
        k2 = build_cache_key(owner="content_strategy", tenant_id=tenant, identity="b")
        other = build_cache_key(owner="content_strategy", tenant_id=uuid4(), identity="a")
        await cache.set_json(k1, {"x": 1}, policy=policy)
        await cache.set_json(k2, {"x": 2}, policy=policy)
        await cache.set_json(other, {"x": 3}, policy=policy)
        deleted = await cache.invalidate_owner(owner="content_strategy", tenant_id=tenant)
        assert deleted == 2
        assert await cache.get_json(other, policy=policy) == {"x": 3}

    asyncio.run(_run())


def test_module_exports_singleton() -> None:
    assert tenant_cache is not None
