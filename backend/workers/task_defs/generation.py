from __future__ import annotations

from uuid import UUID

from backend.modules.content_generation.service import ContentGenerationService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.generate_content_task")
def generate_content_task(*, tenant_id: str, plan_id: str, feedback: str | None = None) -> dict[str, str]:
    async def operation(db):
        job = await ContentGenerationService(db).generate(
            tenant_id=UUID(tenant_id),
            plan_id=UUID(plan_id),
            feedback=feedback,
        )
        return {"job_id": str(job.id)}

    return run_async_task(
        task_name="generate_content",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="content_plan",
        entity_id=plan_id,
        celery_task_id=generate_content_task.request.id,
        correlation_id=generate_content_task.request.id,
        payload=enqueue_payload(plan_id=plan_id),
        operation=operation,
    )
