"""Phase 12 — enrichment LLM cache avoids duplicate Ollama calls."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from backend.modules.inference.enrichment_cache import (
    EMBED_INPUT_VERSION,
    SUMMARIZE_PROMPT_VERSION,
    cached_embedding,
    cached_summary,
    enrichment_cache_key,
    enrichment_content_hash,
)


def test_enrichment_hash_ignores_url_but_tracks_body() -> None:
    a = enrichment_content_hash(title="Hello World!", body="same body")
    b = enrichment_content_hash(title="hello world", body="same body")
    c = enrichment_content_hash(title="Hello World!", body="different")
    assert a == b
    assert a != c


def test_cache_key_changes_with_model_and_prompt_version() -> None:
    tenant = uuid4()
    content_hash = "abc"
    k1 = enrichment_cache_key(
        tenant_id=tenant,
        content_hash=content_hash,
        operation="summarize",
        model="llama3.2:3b",
        prompt_version=SUMMARIZE_PROMPT_VERSION,
    )
    k2 = enrichment_cache_key(
        tenant_id=tenant,
        content_hash=content_hash,
        operation="summarize",
        model="llama3.2:3b",
        prompt_version="summarize.v2.max_words=60",
    )
    k3 = enrichment_cache_key(
        tenant_id=tenant,
        content_hash=content_hash,
        operation="summarize",
        model="other-model",
        prompt_version=SUMMARIZE_PROMPT_VERSION,
    )
    assert k1 != k2
    assert k1 != k3
    assert EMBED_INPUT_VERSION in enrichment_cache_key(
        tenant_id=tenant,
        content_hash=content_hash,
        operation="embed",
        model="nomic",
        prompt_version=EMBED_INPUT_VERSION,
    )


def test_cached_embedding_reuses_factory_result(monkeypatch) -> None:
    store: dict[str, object] = {}
    calls = {"n": 0}

    class FakeCache:
        async def get_or_set(self, key, *, policy, factory, legacy_keys=None):  # noqa: ANN001
            if key in store:
                return store[key]
            value = await factory()
            store[key] = value
            return value

    monkeypatch.setattr(
        "backend.modules.inference.enrichment_cache.tenant_cache",
        FakeCache(),
    )

    async def factory() -> list[float]:
        calls["n"] += 1
        return [0.1, 0.2, 0.3]

    async def run() -> None:
        tenant = uuid4()
        first = await cached_embedding(
            tenant_id=tenant, title="T", body="B", model="nomic", factory=factory
        )
        second = await cached_embedding(
            tenant_id=tenant, title="T", body="B", model="nomic", factory=factory
        )
        assert first == second == [0.1, 0.2, 0.3]
        assert calls["n"] == 1

    asyncio.run(run())


def test_cached_summary_invalidates_on_prompt_version(monkeypatch) -> None:
    store: dict[str, object] = {}
    calls = {"n": 0}

    class FakeCache:
        async def get_or_set(self, key, *, policy, factory, legacy_keys=None):  # noqa: ANN001
            if key in store:
                return store[key]
            value = await factory()
            store[key] = value
            return value

    monkeypatch.setattr(
        "backend.modules.inference.enrichment_cache.tenant_cache",
        FakeCache(),
    )

    async def factory() -> str:
        calls["n"] += 1
        return f"summary-{calls['n']}"

    async def run() -> None:
        tenant = uuid4()
        a = await cached_summary(
            tenant_id=tenant, title="T", body="B", model="llama", max_words=60, factory=factory
        )
        b = await cached_summary(
            tenant_id=tenant, title="T", body="B", model="llama", max_words=60, factory=factory
        )
        c = await cached_summary(
            tenant_id=tenant, title="T", body="B", model="llama", max_words=80, factory=factory
        )
        assert a == b == "summary-1"
        assert c == "summary-2"
        assert calls["n"] == 2

    asyncio.run(run())
