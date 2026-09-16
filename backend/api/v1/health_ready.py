"""Readiness assembly including Alembic schema-revision gate."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import cast

from pydantic import BaseModel
from sqlalchemy import text

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.db.schema_revision import check_schema_revision
from backend.modules.inference.capabilities import ProviderHealth
from backend.modules.inference.providers import collect_inference_readiness, get_inference_metrics_snapshot
from backend.modules.operations.service import OperationsService


class WorkerTaskSnapshot(BaseModel):
    task_name: str
    status: str
    progress: int
    started_at: str | None = None
    finished_at: str | None = None


class WorkerQueueStatus(BaseModel):
    queue_name: str
    running: int
    failed: int
    completed: int
    broker_depth: int | None = None
    recent_tasks: list[WorkerTaskSnapshot]


class ReadinessResponse(BaseModel):
    status: str
    checked_at: str
    checks: dict[str, str]
    inference_providers: dict[str, object]
    inference_metrics: dict[str, object]
    worker_status: list[WorkerQueueStatus]
    components: dict[str, dict[str, object]]
    timings_ms: dict[str, float]


async def build_readiness() -> tuple[ReadinessResponse, int]:
    """Return readiness body + HTTP status (503 when DB/migrations unsafe)."""

    async def check_database() -> tuple[str, list[dict[str, object]], float]:
        started = time.perf_counter()
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            worker_status = await OperationsService(db).worker_status()
        return "ok", worker_status, (time.perf_counter() - started) * 1000.0

    async def check_migrations() -> tuple[dict[str, object], float]:
        started = time.perf_counter()
        migration = await asyncio.to_thread(check_schema_revision)
        return migration.as_component(), (time.perf_counter() - started) * 1000.0

    async def check_redis() -> tuple[str, float]:
        started = time.perf_counter()
        await redis_client.ping()
        return "ok", (time.perf_counter() - started) * 1000.0

    async def check_inference() -> tuple[dict[str, ProviderHealth], float]:
        started = time.perf_counter()
        result = await collect_inference_readiness()
        return result, (time.perf_counter() - started) * 1000.0

    timeout = settings.HEALTH_CHECK_TIMEOUT_SECONDS
    database_result, migration_result, redis_result, inference_result = await asyncio.gather(
        asyncio.wait_for(check_database(), timeout=timeout),
        asyncio.wait_for(check_migrations(), timeout=timeout),
        asyncio.wait_for(check_redis(), timeout=timeout),
        asyncio.wait_for(check_inference(), timeout=timeout),
        return_exceptions=True,
    )

    components: dict[str, dict[str, object]] = {}
    checks: dict[str, str] = {}
    worker_status: list[dict[str, object]] = []

    if isinstance(database_result, BaseException):
        components["database"] = {
            "status": "error",
            "detail": str(database_result),
            "latency_ms": round(timeout * 1000, 2),
        }
    else:
        db_status, worker_status, db_latency_ms = database_result
        components["database"] = {"status": db_status, "latency_ms": round(db_latency_ms, 2)}
    checks["db"] = str(components["database"]["status"])

    if isinstance(migration_result, BaseException):
        components["migrations"] = {
            "status": "error",
            "detail": str(migration_result),
            "latency_ms": round(timeout * 1000, 2),
        }
    else:
        migration_component, mig_latency = migration_result
        components["migrations"] = {
            **migration_component,
            "latency_ms": round(mig_latency, 2),
        }
    checks["migrations"] = str(components["migrations"]["status"])

    if isinstance(redis_result, BaseException):
        components["redis"] = {
            "status": "error",
            "detail": str(redis_result),
            "latency_ms": round(timeout * 1000, 2),
        }
    else:
        redis_status, redis_latency_ms = redis_result
        components["redis"] = {"status": redis_status, "latency_ms": round(redis_latency_ms, 2)}
    checks["redis"] = str(components["redis"]["status"])

    inference_failed = isinstance(inference_result, BaseException)
    if inference_failed:
        inference_providers: dict[str, ProviderHealth] = {}
        inference_latency_ms = timeout * 1000
    else:
        inference_payload = cast(tuple[dict[str, ProviderHealth], float], inference_result)
        inference_providers, inference_latency_ms = inference_payload
    inference_checks = {
        name: {
            "status": health.status,
            "detail": health.detail,
            "models": list(health.models),
        }
        for name, health in inference_providers.items()
    }
    configured_provider = settings.LLM_PROVIDER.lower()
    required_provider = "openai_compatible" if configured_provider == "openai" else configured_provider
    required_health = inference_providers.get(required_provider)
    inference_status = (
        "error"
        if inference_failed
        else "ok" if required_health is None or required_health.status in {"ok", "disabled"} else "error"
    )
    components["inference"] = {
        "status": inference_status,
        "required_provider": required_provider,
        "providers": inference_checks,
        "latency_ms": round(inference_latency_ms, 2),
    }
    checks["inference"] = inference_status
    checks["queues"] = "ok" if settings.celery_broker_url else "error"
    components["queues"] = {"status": checks["queues"], "latency_ms": 0.0}

    hard_fail = checks["db"] != "ok" or checks["migrations"] != "ok"
    soft_ok = all(value == "ok" for value in checks.values())
    status = "error" if hard_fail else ("ok" if soft_ok else "degraded")
    http_status = 503 if hard_fail else 200

    body = ReadinessResponse(
        status=status,
        checked_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        inference_providers=cast(dict[str, object], inference_checks),
        inference_metrics=cast(dict[str, object], get_inference_metrics_snapshot()),
        worker_status=[WorkerQueueStatus.model_validate(item) for item in worker_status],
        components=components,
        timings_ms={
            name: float(str(component["latency_ms"]))
            for name, component in components.items()
        },
    )
    return body, http_status
