from __future__ import annotations

from uuid import UUID

from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.run_chess_catalog_job_task")
def run_chess_catalog_job_task(*, tenant_id: str, job_id: str) -> dict[str, str]:
    """PGN/puzzle import, famous enrich, critical-moment extract, provider sync."""

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
