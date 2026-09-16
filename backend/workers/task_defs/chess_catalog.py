"""Chess catalog Celery tasks — process jobs + config-driven fanouts (§11)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.core.config import settings
from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJobKind
from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.workers.runtime import run_async_task, run_async_task_simple
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.run_chess_catalog_job_task")
def run_chess_catalog_job_task(*, tenant_id: str, job_id: str) -> dict[str, str]:
    """PGN/puzzle import, famous enrich, daily puzzle, provider sync, critical moments."""

    async def operation(db):
        job = await ChessCatalogJobService(db).process_job(
            tenant_id=UUID(tenant_id),
            job_id=UUID(job_id),
            celery_task_id=run_chess_catalog_job_task.request.id,
        )
        return {"job_id": str(job.id), "status": job.status, "kind": job.kind}

    return run_async_task(
        task_name="run_chess_catalog_job",
        queue_name="ingestion",
        tenant_id=UUID(tenant_id),
        entity_type="chess_catalog_job",
        entity_id=job_id,
        celery_task_id=run_chess_catalog_job_task.request.id,
        correlation_id=run_chess_catalog_job_task.request.id,
        payload=enqueue_payload(job_id=job_id, kind="chess_catalog"),
        operation=operation,
    )


def _dispatch_queued_jobs(jobs: list[tuple[str, str]]) -> None:
    """Celery delay after DB commit so workers see persisted ChessCatalogJob rows."""
    for tenant_id, job_id in jobs:
        run_chess_catalog_job_task.delay(tenant_id=tenant_id, job_id=job_id)


@_task("backend.workers.tasks.chess_catalog_daily_puzzle_fanout_task")
def chess_catalog_daily_puzzle_fanout_task() -> dict[str, Any]:
    """Beat: enqueue ``daily_puzzle_sync`` ChessCatalogJob per active tenant."""

    async def operation(db) -> dict[str, Any]:
        from backend.modules.identity_access.repository import TenantRepository

        tenants = await TenantRepository(db).list_active_tenants()
        svc = ChessCatalogJobService(db)
        queued: list[tuple[str, str]] = []
        for tenant in tenants:
            job = await svc.enqueue(
                tenant_id=tenant.id,
                user_id=None,
                kind=ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
                params={"via": "celery_beat"},
            )
            queued.append((str(tenant.id), str(job.id)))
        return {
            "kind": ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
            "tenants_dispatched": len(queued),
            "jobs": queued,
        }

    result = run_async_task_simple(operation)
    _dispatch_queued_jobs(list(result.get("jobs") or []))
    return {
        "kind": result["kind"],
        "tenants_dispatched": int(result["tenants_dispatched"]),
    }


@_task("backend.workers.tasks.chess_catalog_provider_sync_fanout_task")
def chess_catalog_provider_sync_fanout_task() -> dict[str, Any]:
    """Beat: enqueue incremental ``provider_sync`` per tenant (config provider/max)."""

    async def operation(db) -> dict[str, Any]:
        from backend.modules.identity_access.repository import TenantRepository

        tenants = await TenantRepository(db).list_active_tenants()
        svc = ChessCatalogJobService(db)
        params = {
            "provider": settings.CHESS_SCHEDULE_PROVIDER_SYNC_PROVIDER,
            "max_games": settings.CHESS_SCHEDULE_PROVIDER_SYNC_MAX_GAMES,
            "via": "celery_beat",
        }
        queued: list[tuple[str, str]] = []
        for tenant in tenants:
            job = await svc.enqueue(
                tenant_id=tenant.id,
                user_id=None,
                kind=ChessCatalogJobKind.PROVIDER_SYNC.value,
                params=params,
            )
            queued.append((str(tenant.id), str(job.id)))
        return {
            "kind": ChessCatalogJobKind.PROVIDER_SYNC.value,
            "tenants_dispatched": len(queued),
            "jobs": queued,
            "provider": params["provider"],
        }

    result = run_async_task_simple(operation)
    _dispatch_queued_jobs(list(result.get("jobs") or []))
    return {
        "kind": result["kind"],
        "tenants_dispatched": int(result["tenants_dispatched"]),
        "provider": result.get("provider"),
    }
