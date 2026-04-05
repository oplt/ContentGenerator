from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.db.session import engine

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready")
async def ready() -> dict[str, object]:
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

    checks["queues"] = "ok" if settings.celery_broker_url else "error"
    all_ok = all(value == "ok" for value in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@health_router.get("/version")
async def version() -> dict[str, str]:
    return {
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "version": "0.1.0",
        "async_jobs": "celery",
    }
