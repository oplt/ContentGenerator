from __future__ import annotations

from uuid import UUID

from backend.modules.trending_repos.service import TrendingReposService
from backend.workers.runtime import run_async_task, run_async_task_simple
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.fetch_trending_repos_task")
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
        payload=enqueue_payload(tenant_id=tenant_id),
        operation=operation,
    )


@_task("backend.workers.tasks.send_trending_repos_digest_task")
def send_trending_repos_digest_task(*, tenant_id: str) -> dict[str, str]:
    """
    Generate product ideas for today's daily trending repos and send a
    Telegram digest with repos + ideas to the tenant's configured chat.
    """

    async def operation(db) -> dict[str, str]:
        svc = TrendingReposService(db)
        tid = UUID(tenant_id)
        updated = await svc.generate_ideas_for_daily_snapshot(tid)
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
        payload=enqueue_payload(tenant_id=tenant_id),
        operation=operation,
    )


@_task("backend.workers.tasks.trending_repos_daily_fanout_task")
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
                countdown=300,
            )
            dispatched += 1
        return {"tenants_dispatched": dispatched}

    return run_async_task_simple(operation)
