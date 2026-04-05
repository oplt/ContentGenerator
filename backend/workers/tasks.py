from __future__ import annotations

from uuid import UUID

from backend.modules.analytics.service import AnalyticsService
from backend.modules.approvals.service import ApprovalService
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.source_ingestion.service import SourceIngestionService
from backend.modules.publishing.service import PublishingService
from backend.workers.celery_app import celery_app
from backend.workers.email import send_email_sync
from backend.workers.runtime import run_async_task


@celery_app.task(
    name="backend.workers.tasks.send_email_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_email_task(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> None:
    send_email_sync(to=to, subject=subject, html_body=html_body, text_body=text_body)


@celery_app.task(
    name="backend.workers.tasks.poll_sources_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def poll_sources_task() -> list[dict[str, str | int]]:
    def operation(db):
        return SourceIngestionService(db).poll_due_sources()

    results = run_async_task(
        task_name="poll_sources",
        queue_name="ingestion",
        tenant_id=None,
        entity_type="source",
        entity_id=None,
        celery_task_id=poll_sources_task.request.id,
        correlation_id=poll_sources_task.request.id,
        payload={},
        operation=operation,
    )
    return [result.model_dump() for result in results]


@celery_app.task(
    name="backend.workers.tasks.ingest_source_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
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
        payload={"source_id": source_id},
        operation=operation,
    )
    return result.model_dump()


@celery_app.task(
    name="backend.workers.tasks.generate_content_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def generate_content_task(*, tenant_id: str, plan_id: str, feedback: str | None = None) -> dict[str, str]:
    async def operation(db):
        job = await ContentGenerationService(db).generate(
            tenant_id=UUID(tenant_id),
            plan_id=UUID(plan_id),
            feedback=feedback,
        )
        await db.commit()
        return {"job_id": str(job.id)}

    return run_async_task(
        task_name="generate_content",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="content_plan",
        entity_id=plan_id,
        celery_task_id=generate_content_task.request.id,
        correlation_id=generate_content_task.request.id,
        payload={"plan_id": plan_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.send_approval_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_approval_task(*, tenant_id: str, content_job_id: str, recipient: str | None = None) -> dict[str, str]:
    async def operation(db):
        request = await ApprovalService(db).send_for_approval(
            tenant_id=UUID(tenant_id),
            content_job_id=UUID(content_job_id),
            recipient=recipient,
        )
        await db.commit()
        return {"approval_request_id": str(request.id)}

    return run_async_task(
        task_name="send_approval",
        queue_name="approvals",
        tenant_id=UUID(tenant_id),
        entity_type="content_job",
        entity_id=content_job_id,
        celery_task_id=send_approval_task.request.id,
        correlation_id=send_approval_task.request.id,
        payload={"content_job_id": content_job_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.publish_due_jobs_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def publish_due_jobs_task() -> list[str]:
    async def operation(db):
        jobs = await PublishingService(db).execute_due_jobs()
        await db.commit()
        return [str(job.id) for job in jobs]

    return run_async_task(
        task_name="publish_due_jobs",
        queue_name="publishing",
        tenant_id=None,
        entity_type="publishing_job",
        entity_id=None,
        celery_task_id=publish_due_jobs_task.request.id,
        correlation_id=publish_due_jobs_task.request.id,
        payload={},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.sync_analytics_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def sync_analytics_task(*, tenant_id: str) -> int:
    async def operation(db):
        snapshots = await AnalyticsService(db).sync_snapshots(UUID(tenant_id))
        await db.commit()
        return len(snapshots)

    return run_async_task(
        task_name="sync_analytics",
        queue_name="analytics",
        tenant_id=UUID(tenant_id),
        entity_type="analytics_snapshot",
        entity_id=None,
        celery_task_id=sync_analytics_task.request.id,
        correlation_id=sync_analytics_task.request.id,
        payload={"tenant_id": tenant_id},
        operation=operation,
    )
