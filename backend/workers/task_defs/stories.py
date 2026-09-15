from __future__ import annotations

from uuid import UUID

from backend.modules.story_intelligence.service import StoryIntelligenceService
from backend.workers.runtime import run_async_task, run_async_task_simple
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.rescore_clusters_task")
def rescore_clusters_task(*, tenant_id: str) -> int:
    async def operation(db):
        count = await StoryIntelligenceService(db).rescore_active_clusters(UUID(tenant_id))
        return count

    return run_async_task(
        task_name="rescore_clusters",
        queue_name="enrichment",
        tenant_id=UUID(tenant_id),
        entity_type="story_cluster",
        entity_id=None,
        celery_task_id=rescore_clusters_task.request.id,
        correlation_id=rescore_clusters_task.request.id,
        payload=enqueue_payload(tenant_id=tenant_id),
        operation=operation,
    )


@_task("backend.workers.tasks.rescore_all_tenants_task")
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
