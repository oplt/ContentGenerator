from __future__ import annotations

from uuid import UUID

from backend.modules.analytics.service import AnalyticsService
from backend.modules.trending_repos.service import TrendingReposService
from backend.modules.approvals.service import ApprovalService
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.source_ingestion.service import SourceIngestionService
from backend.modules.publishing.service import PublishingService
from backend.modules.story_intelligence.service import StoryIntelligenceService
from backend.workers.celery_app import celery_app
from backend.workers.email import send_email_sync
from backend.workers.runtime import run_async_task, run_async_task_simple


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
    # Pass the Celery task ID as worker_id for traceability in the DB
    worker_id = publish_due_jobs_task.request.id or "beat-worker"

    async def operation(db):
        jobs = await PublishingService(db).execute_due_jobs(worker_id=worker_id)
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
    name="backend.workers.tasks.process_webhook_inbox_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def process_webhook_inbox_task(*, inbox_id: str) -> dict[str, int]:
    async def operation(db):
        service = ApprovalService(db)
        updated = await service.process_webhook_inbox(UUID(inbox_id))
        return {"updated_requests": len(updated)}

    return run_async_task(
        task_name="process_webhook_inbox",
        queue_name="approvals",
        tenant_id=None,
        entity_type="webhook_inbox",
        entity_id=inbox_id,
        celery_task_id=process_webhook_inbox_task.request.id,
        correlation_id=process_webhook_inbox_task.request.id,
        payload={"inbox_id": inbox_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.expire_stale_approvals_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def expire_stale_approvals_task() -> int:
    async def operation(db):
        from datetime import datetime, timezone
        from backend.modules.approvals.models import ApprovalStatus
        repo = ApprovalService(db).repo
        expired = await repo.list_expired_pending_requests()
        for request in expired:
            request.status = ApprovalStatus.EXPIRED.value
        await db.commit()
        return len(expired)

    return run_async_task(
        task_name="expire_stale_approvals",
        queue_name="approvals",
        tenant_id=None,
        entity_type="approval_request",
        entity_id=None,
        celery_task_id=expire_stale_approvals_task.request.id,
        correlation_id=expire_stale_approvals_task.request.id,
        payload={},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.expire_stale_briefs_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def expire_stale_briefs_task(*, tenant_id: str) -> int:
    """Mark READY editorial briefs past their expires_at as EXPIRED."""
    async def operation(db):
        from backend.modules.editorial_briefs.service import EditorialBriefService
        count = await EditorialBriefService(db).expire_stale_briefs(UUID(tenant_id))
        await db.commit()
        return count

    return run_async_task(
        task_name="expire_stale_briefs",
        queue_name="approvals",
        tenant_id=UUID(tenant_id),
        entity_type="editorial_brief",
        entity_id=None,
        celery_task_id=expire_stale_briefs_task.request.id,
        correlation_id=expire_stale_briefs_task.request.id,
        payload={"tenant_id": tenant_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.rescore_clusters_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def rescore_clusters_task(*, tenant_id: str) -> int:
    async def operation(db):
        count = await StoryIntelligenceService(db).rescore_active_clusters(UUID(tenant_id))
        await db.commit()
        return count

    return run_async_task(
        task_name="rescore_clusters",
        queue_name="enrichment",
        tenant_id=UUID(tenant_id),
        entity_type="story_cluster",
        entity_id=None,
        celery_task_id=rescore_clusters_task.request.id,
        correlation_id=rescore_clusters_task.request.id,
        payload={"tenant_id": tenant_id},
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


@celery_app.task(
    name="backend.workers.tasks.fetch_trending_repos_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def fetch_trending_repos_task(*, tenant_id: str) -> dict[str, int]:
    """
    Refresh trending repos snapshot for all three periods (daily/weekly/monthly)
    and then trigger product-idea generation for today's daily batch.
    """
    async def operation(db) -> dict[str, int]:
        svc = TrendingReposService(db)
        tid = UUID(tenant_id)
        counts: dict[str, int] = {}
        for period in ("daily", "weekly", "monthly"):
            try:
                records = await svc.refresh_snapshot(tid, period)
                counts[period] = len(records)
            except Exception:  # pragma: no cover
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to fetch %s trending repos for tenant %s", period, tenant_id
                )
                counts[period] = 0
        return counts

    return run_async_task(
        task_name="fetch_trending_repos",
        queue_name="enrichment",
        tenant_id=UUID(tenant_id),
        entity_type="trending_repo",
        entity_id=None,
        celery_task_id=fetch_trending_repos_task.request.id,
        correlation_id=fetch_trending_repos_task.request.id,
        payload={"tenant_id": tenant_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.send_trending_repos_digest_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_trending_repos_digest_task(*, tenant_id: str) -> dict[str, str]:
    """
    Generate product ideas for today's daily trending repos and send a
    Telegram digest with repos + ideas to the tenant's configured chat.
    """
    async def operation(db) -> dict[str, str]:
        svc = TrendingReposService(db)
        tid = UUID(tenant_id)
        # Generate product ideas for all daily repos
        updated = await svc.generate_ideas_for_daily_snapshot(tid)
        # Send Telegram digest
        await svc.send_daily_digest_to_telegram(tid)
        return {"repos_with_ideas": str(len(updated))}

    return run_async_task(
        task_name="send_trending_repos_digest",
        queue_name="enrichment",
        tenant_id=UUID(tenant_id),
        entity_type="trending_repo",
        entity_id=None,
        celery_task_id=send_trending_repos_digest_task.request.id,
        correlation_id=send_trending_repos_digest_task.request.id,
        payload={"tenant_id": tenant_id},
        operation=operation,
    )


@celery_app.task(
    name="backend.workers.tasks.trending_repos_daily_fanout_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def trending_repos_daily_fanout_task() -> dict[str, int]:
    """
    Beat-schedulable fan-out: fetches all active tenants, dispatches
    fetch_trending_repos_task + send_trending_repos_digest_task per tenant.
    """
    async def operation(db) -> dict[str, int]:
        from backend.modules.identity_access.repository import TenantRepository
        repo = TenantRepository(db)
        tenants = await repo.list_active_tenants()
        dispatched = 0
        for tenant in tenants:
            fetch_trending_repos_task.delay(tenant_id=str(tenant.id))
            send_trending_repos_digest_task.apply_async(
                kwargs={"tenant_id": str(tenant.id)},
                countdown=300,  # run 5 min after fetch to ensure data is ready
            )
            dispatched += 1
        return {"tenants_dispatched": dispatched}

    return run_async_task_simple(operation)


@celery_app.task(
    name="backend.workers.tasks.rescore_all_tenants_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2,
)
def rescore_all_tenants_task() -> dict[str, int]:
    """
    Beat-schedulable fan-out task: fetches all active tenants and dispatches
    rescore_clusters_task per tenant. No tenant_id required at schedule time.
    """
    async def operation(db) -> dict[str, int]:
        from backend.modules.identity_access.repository import TenantRepository
        repo = TenantRepository(db)
        tenants = await repo.list_active_tenants()
        dispatched = 0
        for tenant in tenants:
            rescore_clusters_task.delay(tenant_id=str(tenant.id))
            dispatched += 1
        return {"tenants_dispatched": dispatched}

    return run_async_task_simple(operation)
