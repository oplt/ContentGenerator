from __future__ import annotations

from uuid import UUID

from backend.modules.source_ingestion.ingestion_workflow import run_ingestion_workflow
from backend.modules.source_ingestion.service import SourceIngestionService
from backend.workers.runtime import run_async_task, run_detached_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task
from backend.workers.task_lock import periodic_task_lock


@_task("backend.workers.tasks.poll_sources_task")
def poll_sources_task() -> dict[str, int]:
    """
    Fan-out due sources to per-source ingest tasks (queue-isolated, bounded).

    Keeps the beat tick short; heavy fetch/dedupe runs on ingest_source_task.
    """

    async def operation(db) -> dict[str, int]:
        async with periodic_task_lock("poll_sources", ttl_seconds=240) as acquired:
            if not acquired:
                return {"dispatched": 0, "skipped": 1}
            sources = await SourceIngestionService(db).repo.list_due_sources()
            for source in sources:
                ingest_source_task.delay(
                    tenant_id=str(source.tenant_id),
                    source_id=str(source.id),
                )
            return {"dispatched": len(sources), "skipped": 0}

    return run_async_task(
        task_name="poll_sources",
        queue_name="ingestion",
        tenant_id=None,
        entity_type="source",
        entity_id=None,
        celery_task_id=poll_sources_task.request.id,
        correlation_id=poll_sources_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )


@_task("backend.workers.tasks.ingest_source_task")
def ingest_source_task(
    *,
    tenant_id: str,
    source_id: str,
    fetch_run_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, str | int | None]:
    """Per-source ingest with no worker DB hold across network fetch."""

    async def operation():
        return await run_ingestion_workflow(
            tenant_id=UUID(tenant_id),
            source_id=UUID(source_id),
            fetch_run_id=UUID(fetch_run_id) if fetch_run_id else None,
        )

    result = run_detached_async_task(
        task_name="ingest_source",
        queue_name="ingestion",
        tenant_id=UUID(tenant_id),
        entity_type="source",
        entity_id=source_id,
        celery_task_id=ingest_source_task.request.id,
        correlation_id=correlation_id or ingest_source_task.request.id,
        payload=enqueue_payload(
            source_id=source_id,
            fetch_run_id=fetch_run_id or "",
            correlation_id=correlation_id or "",
        ),
        operation=operation,
    )
    return result.model_dump()
