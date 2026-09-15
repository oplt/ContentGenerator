"""Phase 4 — bounded, concurrent readiness checks."""

from __future__ import annotations

import asyncio
import time

from backend.api.v1 import health
from backend.modules.inference.capabilities import ProviderHealth


def test_readiness_checks_dependencies_concurrently(monkeypatch) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement):
            await asyncio.sleep(0.03)

    class FakeOperations:
        def __init__(self, db):
            pass

        async def worker_status(self):
            await asyncio.sleep(0.03)
            return []

    class FakeRedis:
        async def ping(self):
            await asyncio.sleep(0.03)

    async def fake_inference_readiness():
        await asyncio.sleep(0.03)
        return {
            "ollama": ProviderHealth("ollama", "ok"),
            "vllm": ProviderHealth("vllm", "error", "optional unavailable"),
            "llamacpp": ProviderHealth("llamacpp", "error", "optional unavailable"),
        }

    monkeypatch.setattr("backend.db.session.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(health, "OperationsService", FakeOperations)
    monkeypatch.setattr(health, "redis_client", FakeRedis())
    monkeypatch.setattr(health, "collect_inference_readiness", fake_inference_readiness)

    started = time.perf_counter()
    response = asyncio.run(health.ready())
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert response.status == "ok"
    assert response.checks["inference"] == "ok"
    assert response.components["database"]["latency_ms"] >= 0
    assert response.components["redis"]["latency_ms"] >= 0
    assert response.components["inference"]["required_provider"] == "ollama"
