from __future__ import annotations

from uuid import UUID

from backend.modules.approvals.service import ApprovalService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.send_approval_task")
def send_approval_task(*, tenant_id: str, content_job_id: str, recipient: str | None = None) -> dict[str, str]:
    async def operation(db):
        request = await ApprovalService(db).send_for_approval(
            tenant_id=UUID(tenant_id),
            content_job_id=UUID(content_job_id),
            recipient=recipient,
        )
        return {"approval_request_id": str(request.id)}

    return run_async_task(
        task_name="send_approval",
        queue_name="approvals",
        tenant_id=UUID(tenant_id),
        entity_type="content_job",
        entity_id=content_job_id,
        celery_task_id=send_approval_task.request.id,
        correlation_id=send_approval_task.request.id,
        payload=enqueue_payload(content_job_id=content_job_id),
        operation=operation,
    )


@_task("backend.workers.tasks.process_webhook_inbox_task")
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
        payload=enqueue_payload(inbox_id=inbox_id),
        operation=operation,
    )


@_task("backend.workers.tasks.expire_stale_approvals_task")
def expire_stale_approvals_task() -> int:
    async def operation(db):
        from backend.modules.approvals.models import ApprovalStatus
        from backend.modules.workflows.approval_binding import (
            maybe_resume_workflow_from_approval,
        )

        repo = ApprovalService(db).repo
        expired = await repo.list_expired_pending_requests()
        for request in expired:
            request.status = ApprovalStatus.EXPIRED.value
            await maybe_resume_workflow_from_approval(db, request)
        return len(expired)

    return run_async_task(
        task_name="expire_stale_approvals",
        queue_name="approvals",
        tenant_id=None,
        entity_type="approval_request",
        entity_id=None,
        celery_task_id=expire_stale_approvals_task.request.id,
        correlation_id=expire_stale_approvals_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )


@_task("backend.workers.tasks.expire_stale_briefs_task")
def expire_stale_briefs_task(*, tenant_id: str) -> int:
    """Mark READY editorial briefs past their expires_at as EXPIRED."""

    async def operation(db):
        from backend.modules.editorial_briefs.service import EditorialBriefService

        count = await EditorialBriefService(db).expire_stale_briefs(UUID(tenant_id))
        return count

    return run_async_task(
        task_name="expire_stale_briefs",
        queue_name="approvals",
        tenant_id=UUID(tenant_id),
        entity_type="editorial_brief",
        entity_id=None,
        celery_task_id=expire_stale_briefs_task.request.id,
        correlation_id=expire_stale_briefs_task.request.id,
        payload=enqueue_payload(tenant_id=tenant_id),
        operation=operation,
    )
