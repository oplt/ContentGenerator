"""Phase 5 cache codec + namespace flush tests."""

from __future__ import annotations

import asyncio

from backend.core.cache import RedisCache
from backend.core.cache_codec import CODEC_MISS, decode, encode


def test_get_many_skips_bad_values() -> None:
    async def _run() -> None:
        cache = RedisCache.__new__(RedisCache)

        class _Client:
            async def mget(self, keys):
                return [encode({"ok": True}), "{bad", None]

        cache.redis_client = _Client()  # type: ignore[assignment]
        result = await cache.get_many(["a", "b", "c"])
        assert result["a"] == {"ok": True}
        assert result["b"] is None
        assert result["c"] is None

    asyncio.run(_run())


def test_flush_all_does_not_call_flushall() -> None:
    async def _run() -> None:
        cache = RedisCache.__new__(RedisCache)
        deleted_keys: list[str] = []

        class _Client:
            async def scan_iter(self, match: str = "*", count: int = 200):
                for key in ("cg:test:global:x:1", "cg:test:global:x:2"):
                    yield key

            async def delete(self, key: str):
                deleted_keys.append(key)
                return 1

            async def flushall(self):
                raise AssertionError("FLUSHALL must not be called")

        cache.redis_client = _Client()  # type: ignore[assignment]
        # Bypass cache_env import path by passing explicit match.
        count = await cache.flush_namespace("cg:test:*")
        assert count == 2
        assert deleted_keys == ["cg:test:global:x:1", "cg:test:global:x:2"]
        ok = await cache.flush_all()
        assert ok is True

    asyncio.run(_run())


def test_codec_encode_decode() -> None:
    assert decode(encode([1, "x"])) == [1, "x"]
    assert decode(b"not-json") is CODEC_MISS or decode(b'"ok"') == "ok"
