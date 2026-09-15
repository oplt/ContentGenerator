from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics, get_domain_metrics_snapshot
from backend.core.http import get_http_stats
from backend.core.tenant_cache import get_cache_stats
from backend.db.session import get_pool_stats
from backend.modules.inference.providers import collect_inference_readiness, get_inference_metrics_snapshot
from backend.modules.operations.service import OperationsService

health_router = APIRouter(prefix="/health", tags=["health"])


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


class VersionResponse(BaseModel):
    app: str
    env: str
    version: str
    async_jobs: str


class WorkloadCapacityStatus(BaseModel):
    workload: str
    queues: list[str]
    concurrency: int
    prefetch_multiplier: int
    db_pool_slots: int
    within_db_budget: bool


class MetricsResponse(BaseModel):
    checked_at: str
    queues: list[WorkerQueueStatus]
    broker_queue_depths: dict[str, int]
    worker_capacity: list[WorkloadCapacityStatus]
    inference_metrics: dict[str, object]
    runtime: dict[str, object]
    domain: dict[str, object]
    cache: dict[str, int]
    http: dict[str, int]
    db_pool: dict[str, int]


class WebVitalSample(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    value: float = Field(ge=0, le=600_000)
    rating: str = Field(default="unknown", max_length=32)
    navigation_type: str = Field(default="unknown", max_length=32)


@health_router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready", response_model=ReadinessResponse)
async def ready() -> ReadinessResponse:
    async def check_database() -> tuple[str, list[dict[str, object]], float]:
        started = time.perf_counter()
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            worker_status = await OperationsService(db).worker_status()
        return "ok", worker_status, (time.perf_counter() - started) * 1000.0

    async def check_redis() -> tuple[str, float]:
        started = time.perf_counter()
        await redis_client.ping()
        return "ok", (time.perf_counter() - started) * 1000.0

    async def check_inference():
        started = time.perf_counter()
        result = await collect_inference_readiness()
        return result, (time.perf_counter() - started) * 1000.0

    timeout = settings.HEALTH_CHECK_TIMEOUT_SECONDS
    database_result, redis_result, inference_result = await asyncio.gather(
        asyncio.wait_for(check_database(), timeout=timeout),
        asyncio.wait_for(check_redis(), timeout=timeout),
        asyncio.wait_for(check_inference(), timeout=timeout),
        return_exceptions=True,
    )

    components: dict[str, dict[str, object]] = {}
    checks: dict[str, str] = {}

    if isinstance(database_result, BaseException):
        components["database"] = {
            "status": "error",
            "detail": str(database_result),
            "latency_ms": round(timeout * 1000, 2),
        }
        worker_status: list[dict[str, object]] = []
    else:
        db_status, worker_status, db_latency_ms = database_result
        components["database"] = {"status": db_status, "latency_ms": round(db_latency_ms, 2)}
    checks["db"] = str(components["database"]["status"])

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
    inference_providers = {} if inference_failed else inference_result[0]
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
        "latency_ms": round(
            timeout * 1000 if inference_failed else inference_result[1],
            2,
        ),
    }
    checks["inference"] = inference_status

    checks["queues"] = "ok" if settings.celery_broker_url else "error"
    all_ok = all(value == "ok" for value in checks.values())
    components["queues"] = {"status": checks["queues"], "latency_ms": 0.0}
    return ReadinessResponse(
        status="ok" if all_ok else "degraded",
        checked_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        inference_providers=cast(dict[str, object], inference_checks),
        inference_metrics=cast(dict[str, object], get_inference_metrics_snapshot()),
        worker_status=[WorkerQueueStatus.model_validate(item) for item in worker_status],
        components=components,
        timings_ms={name: float(component["latency_ms"]) for name, component in components.items()},
    )


@health_router.get("/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    from backend.db.session import SessionLocal
    from backend.workers.queue_depth import broker_queue_depths
    from backend.workers.worker_capacity import capacity_snapshot

    async with SessionLocal() as db:
        worker_status = await OperationsService(db).worker_status()
    depths = await broker_queue_depths()
    enriched: list[WorkerQueueStatus] = []
    for item in worker_status:
        queue_name = str(item.get("queue_name", ""))
        enriched.append(
            WorkerQueueStatus.model_validate(
                {
                    **item,
                    "broker_depth": depths.get(queue_name),
                }
            )
        )
    # Include empty queues that have broker depth but no recent TaskExecution rows.
    seen = {row.queue_name for row in enriched}
    for queue_name, depth in depths.items():
        if queue_name not in seen:
            enriched.append(
                WorkerQueueStatus(
                    queue_name=queue_name,
                    running=0,
                    failed=0,
                    completed=0,
                    broker_depth=depth,
                    recent_tasks=[],
                )
            )
    capacity = [
        WorkloadCapacityStatus(
            workload=row.workload,
            queues=list(row.queues),
            concurrency=row.concurrency,
            prefetch_multiplier=row.prefetch_multiplier,
            db_pool_slots=row.db_pool_slots,
            within_db_budget=row.within_db_budget,
        )
        for row in capacity_snapshot()
    ]
    return MetricsResponse(
        checked_at=datetime.now(timezone.utc).isoformat(),
        queues=enriched,
        broker_queue_depths=depths,
        worker_capacity=capacity,
        inference_metrics=cast(dict[str, object], get_inference_metrics_snapshot()),
        runtime={
            "broker_url_configured": bool(settings.celery_broker_url),
            "analytics_synthetic_mode": settings.ANALYTICS_SYNTHETIC_MODE,
            "social_dry_run_by_default": settings.SOCIAL_DRY_RUN_BY_DEFAULT,
            "multi_account_mode": settings.MULTI_ACCOUNT_ROLLOUT_MODE,
            "multi_account_canary_percent": settings.MULTI_ACCOUNT_CANARY_PERCENT,
            "worker_prefetch_multiplier": settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
        },
        domain=cast(dict[str, object], get_domain_metrics_snapshot()),
        cache=get_cache_stats(),
        http=get_http_stats(),
        db_pool=get_pool_stats(),
    )


@health_router.post("/web-vitals")
async def ingest_web_vitals(sample: WebVitalSample) -> dict[str, str]:
    """Browser beacon for LCP/CLS/INP (and friends). No auth; low-cardinality only."""
    allowed = {"lcp", "cls", "inp", "fcp", "ttfb", "fid"}
    name = sample.name.strip().lower()
    if name not in allowed:
        return {"status": "ignored"}
    domain_metrics.record_web_vital(
        name=name,
        value=sample.value,
        rating=sample.rating,
        navigation_type=sample.navigation_type,
    )
    return {"status": "ok"}


class AppConfigResponse(BaseModel):
    mfa_access: bool
    multi_account_mode: str
    multi_account_canary_percent: int


@health_router.get("/config", response_model=AppConfigResponse)
async def app_config() -> AppConfigResponse:
    """Public endpoint — returns feature flags that the frontend needs before auth."""
    return AppConfigResponse(
        mfa_access=settings.MFA_ACCESS,
        multi_account_mode=settings.MULTI_ACCOUNT_ROLLOUT_MODE,
        multi_account_canary_percent=settings.MULTI_ACCOUNT_CANARY_PERCENT,
    )


@health_router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        app=settings.APP_NAME,
        env=settings.APP_ENV,
        version="0.1.0",
        async_jobs="celery",
    )
