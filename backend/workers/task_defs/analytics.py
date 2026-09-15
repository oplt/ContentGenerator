from __future__ import annotations

from uuid import UUID

from backend.modules.analytics.service import AnalyticsService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.sync_analytics_task")
def sync_analytics_task(*, tenant_id: str) -> int:
    async def operation(db):
        snapshots = await AnalyticsService(db).sync_snapshots(UUID(tenant_id))
        return len(snapshots)

    return run_async_task(
        task_name="sync_analytics",
        queue_name="analytics",
        tenant_id=UUID(tenant_id),
        entity_type="analytics_snapshot",
        entity_id=None,
        celery_task_id=sync_analytics_task.request.id,
        correlation_id=sync_analytics_task.request.id,
        payload=enqueue_payload(tenant_id=tenant_id),
        operation=operation,
    )
