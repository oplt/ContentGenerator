from __future__ import annotations

from backend.modules.publishing.service import PublishingService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task
from backend.workers.task_lock import periodic_task_lock


@_task("backend.workers.tasks.publish_due_jobs_task")
def publish_due_jobs_task() -> list[str]:
    # Pass the Celery task ID as worker_id for traceability in the DB
    worker_id = publish_due_jobs_task.request.id or "beat-worker"

    async def operation(db):
        async with periodic_task_lock("publish_due_jobs", ttl_seconds=240) as acquired:
            if not acquired:
                return []
            jobs = await PublishingService(db).execute_due_jobs(worker_id=worker_id)
            # execute_due_jobs commits claim/attempt boundaries itself.
            return [str(job.id) for job in jobs]

    return run_async_task(
        task_name="publish_due_jobs",
        queue_name="publishing",
        tenant_id=None,
        entity_type="publishing_job",
        entity_id=None,
        celery_task_id=publish_due_jobs_task.request.id,
        correlation_id=publish_due_jobs_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )
