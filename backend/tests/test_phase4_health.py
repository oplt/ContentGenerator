"""Phase 4 — bounded, concurrent readiness checks (+ schema gate)."""

from __future__ import annotations

import asyncio
import time
from typing import cast

from backend.api.v1 import health_ready
from backend.db.schema_revision import SchemaRevisionStatus
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
    monkeypatch.setattr(health_ready, "OperationsService", FakeOperations)
    monkeypatch.setattr(health_ready, "redis_client", FakeRedis())
    monkeypatch.setattr(health_ready, "collect_inference_readiness", fake_inference_readiness)
    monkeypatch.setattr(
        health_ready,
        "check_schema_revision",
        lambda: SchemaRevisionStatus(
            ok=True,
            current="head",
            expected_heads=("head",),
            detail="ok",
        ),
    )

    started = time.perf_counter()
    response, status_code = asyncio.run(health_ready.build_readiness())
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert status_code == 200
    assert response.status == "ok"
    assert response.checks["inference"] == "ok"
    assert response.checks["migrations"] == "ok"
    assert cast(float, response.components["database"]["latency_ms"]) >= 0
    assert cast(float, response.components["redis"]["latency_ms"]) >= 0
    assert response.components["inference"]["required_provider"] == "ollama"


def test_readiness_returns_503_when_migrations_behind(monkeypatch) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def execute(self, statement):
            return None

    class FakeOperations:
        def __init__(self, db):
            pass

        async def worker_status(self):
            return []

    class FakeRedis:
        async def ping(self):
            return True

    async def fake_inference_readiness():
        return {"ollama": ProviderHealth("ollama", "ok")}

    monkeypatch.setattr("backend.db.session.SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(health_ready, "OperationsService", FakeOperations)
    monkeypatch.setattr(health_ready, "redis_client", FakeRedis())
    monkeypatch.setattr(health_ready, "collect_inference_readiness", fake_inference_readiness)
    monkeypatch.setattr(
        health_ready,
        "check_schema_revision",
        lambda: SchemaRevisionStatus(
            ok=False,
            current="c9d0e1f2a3b4",
            expected_heads=("f2a3b4c5d6e7",),
            detail="behind",
        ),
    )

    response, status_code = asyncio.run(health_ready.build_readiness())
    assert status_code == 503
    assert response.status == "error"
    assert response.checks["migrations"] == "error"
