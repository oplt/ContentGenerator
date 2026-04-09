from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.db.session import engine
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
    recent_tasks: list[WorkerTaskSnapshot]


class ReadinessResponse(BaseModel):
    status: str
    checked_at: str
    checks: dict[str, str]
    inference_providers: dict[str, object]
    inference_metrics: dict[str, object]
    worker_status: list[WorkerQueueStatus]


class VersionResponse(BaseModel):
    app: str
    env: str
    version: str
    async_jobs: str


class MetricsResponse(BaseModel):
    checked_at: str
    queues: list[WorkerQueueStatus]
    inference_metrics: dict[str, object]
    runtime: dict[str, object]


@health_router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready", response_model=ReadinessResponse)
async def ready() -> ReadinessResponse:
    checks: dict[str, str] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        checks["db"] = "error"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    inference_providers = await collect_inference_readiness()
    inference_checks = {
        name: {
            "status": health.status,
            "detail": health.detail,
            "models": list(health.models),
        }
        for name, health in inference_providers.items()
    }
    checks["inference"] = (
        "ok"
        if all(health.status in {"ok", "disabled"} for health in inference_providers.values())
        else "error"
    )

    checks["queues"] = "ok" if settings.celery_broker_url else "error"
    all_ok = all(value == "ok" for value in checks.values())
    from backend.db.session import SessionLocal

    async with SessionLocal() as db:
        worker_status = await OperationsService(db).worker_status()
    return ReadinessResponse(
        status="ok" if all_ok else "degraded",
        checked_at=datetime.now(timezone.utc).isoformat(),
        checks=checks,
        inference_providers=inference_checks,
        inference_metrics=get_inference_metrics_snapshot(),
        worker_status=[WorkerQueueStatus.model_validate(item) for item in worker_status],
    )


@health_router.get("/metrics", response_model=MetricsResponse)
async def metrics() -> MetricsResponse:
    from backend.db.session import SessionLocal

    async with SessionLocal() as db:
        worker_status = await OperationsService(db).worker_status()
    return MetricsResponse(
        checked_at=datetime.now(timezone.utc).isoformat(),
        queues=[WorkerQueueStatus.model_validate(item) for item in worker_status],
        inference_metrics=get_inference_metrics_snapshot(),
        runtime={
            "broker_url_configured": bool(settings.celery_broker_url),
            "analytics_synthetic_mode": settings.ANALYTICS_SYNTHETIC_MODE,
            "social_dry_run_by_default": settings.SOCIAL_DRY_RUN_BY_DEFAULT,
        },
    )


class AppConfigResponse(BaseModel):
    mfa_access: bool


@health_router.get("/config", response_model=AppConfigResponse)
async def app_config() -> AppConfigResponse:
    """Public endpoint — returns feature flags that the frontend needs before auth."""
    return AppConfigResponse(mfa_access=settings.MFA_ACCESS)


@health_router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    return VersionResponse(
        app=settings.APP_NAME,
        env=settings.APP_ENV,
        version="0.1.0",
        async_jobs="celery",
    )
