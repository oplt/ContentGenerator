from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from backend.api.v1.health_ready import ReadinessResponse, WorkerQueueStatus, build_readiness
from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics, get_domain_metrics_snapshot
from backend.core.http import get_http_stats
from backend.core.tenant_cache import get_cache_stats
from backend.db.session import get_pool_stats
from backend.modules.inference.providers import get_inference_metrics_snapshot
from backend.modules.operations.service import OperationsService

health_router = APIRouter(prefix="/health", tags=["health"])


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
async def ready(response: Response) -> ReadinessResponse:
    body, status_code = await build_readiness()
    response.status_code = status_code
    return body


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
