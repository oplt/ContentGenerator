from __future__ import annotations

from uuid import UUID

from backend.db.session import get_sessionmaker
from backend.modules.content_generation.image_service import ImageGenerationService
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.content_generation.tts_service import TTSService
from backend.workers.runtime import run_async_task, run_detached_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.generate_content_task")
def generate_content_task(*, tenant_id: str, plan_id: str, feedback: str | None = None) -> dict[str, str]:
    """Generation uses its own session; ledger session is detached around the run."""
    celery_id = generate_content_task.request.id or ""

    async def operation() -> dict[str, str]:
        from backend.core.log_context import bind_log_context

        SessionLocal = get_sessionmaker()
        bind_log_context(
            tenant_id=tenant_id,
            celery_task_id=celery_id or None,
            correlation_id=celery_id or None,
        )
        async with SessionLocal() as db:
            job = await ContentGenerationService(db).generate(
                tenant_id=UUID(tenant_id),
                plan_id=UUID(plan_id),
                feedback=feedback,
            )
            if celery_id:
                job.provider_metadata = {
                    **(job.provider_metadata or {}),
                    "celery_task_id": celery_id,
                    "correlation_id": celery_id,
                }
            await db.commit()
            bind_log_context(content_job_id=job.id, job_id=job.id)
            return {"job_id": str(job.id), "task_id": celery_id or ""}

    return run_detached_async_task(
        task_name="generate_content",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="content_plan",
        entity_id=plan_id,
        celery_task_id=generate_content_task.request.id,
        correlation_id=generate_content_task.request.id,
        payload=enqueue_payload(plan_id=plan_id, celery_task_id=celery_id),
        operation=operation,
    )


@_task("backend.workers.tasks.generate_image_asset_task")
def generate_image_asset_task(
    *,
    tenant_id: str,
    job_id: str,
    headline: str,
    primary_topic: str,
    keywords: str,
    platform: str,
) -> dict[str, str]:
    async def operation(db):
        asset = await ImageGenerationService(db).generate_for_job(
            tenant_id=UUID(tenant_id),
            job_id=UUID(job_id),
            headline=headline,
            primary_topic=primary_topic,
            keywords=keywords,
            platform=platform,
        )
        return {"asset_id": str(asset.id) if asset else ""}

    return run_async_task(
        task_name="generate_image_asset",
        queue_name="video",
        tenant_id=UUID(tenant_id),
        entity_type="content_job",
        entity_id=job_id,
        celery_task_id=generate_image_asset_task.request.id,
        correlation_id=generate_image_asset_task.request.id,
        payload=enqueue_payload(job_id=job_id, kind="image"),
        operation=operation,
    )


@_task("backend.workers.tasks.generate_tts_asset_task")
def generate_tts_asset_task(
    *,
    tenant_id: str,
    job_id: str,
    headline: str,
    summary: str,
    cta: str,
    platform: str,
) -> dict[str, str]:
    async def operation(db):
        asset = await TTSService(db).generate_for_job(
            tenant_id=UUID(tenant_id),
            job_id=UUID(job_id),
            headline=headline,
            summary=summary,
            cta=cta,
            platform=platform,
        )
        return {"asset_id": str(asset.id) if asset else ""}

    return run_async_task(
        task_name="generate_tts_asset",
        queue_name="video",
        tenant_id=UUID(tenant_id),
        entity_type="content_job",
        entity_id=job_id,
        celery_task_id=generate_tts_asset_task.request.id,
        correlation_id=generate_tts_asset_task.request.id,
        payload=enqueue_payload(job_id=job_id, kind="tts"),
        operation=operation,
    )
