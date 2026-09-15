from __future__ import annotations

from uuid import UUID

from backend.modules.source_ingestion.service import SourceIngestionService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.poll_sources_task")
def poll_sources_task() -> dict[str, int]:
    """
    Fan-out due sources to per-source ingest tasks (queue-isolated, bounded).

    Keeps the beat tick short; heavy fetch/dedupe runs on ingest_source_task.
    """

    async def operation(db) -> dict[str, int]:
        sources = await SourceIngestionService(db).repo.list_due_sources()
        for source in sources:
            ingest_source_task.delay(
                tenant_id=str(source.tenant_id),
                source_id=str(source.id),
            )
        return {"dispatched": len(sources)}

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
def ingest_source_task(*, tenant_id: str, source_id: str) -> dict[str, str | int]:
    def operation(db):
        return SourceIngestionService(db).run_ingestion(UUID(tenant_id), UUID(source_id))

    result = run_async_task(
        task_name="ingest_source",
        queue_name="ingestion",
        tenant_id=UUID(tenant_id),
        entity_type="source",
        entity_id=source_id,
        celery_task_id=ingest_source_task.request.id,
        correlation_id=ingest_source_task.request.id,
        payload=enqueue_payload(source_id=source_id),
        operation=operation,
    )
    return result.model_dump()
