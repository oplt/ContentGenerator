"""Celery tasks for workflow automation scheduling (Phase 7)."""

from __future__ import annotations

from uuid import UUID

from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.scheduler import AutomationScheduler
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task
from backend.workers.task_lock import periodic_task_lock


@_task("backend.workers.tasks.tick_due_automations_task")
def tick_due_automations_task() -> list[dict[str, str | None]]:
    async def operation(db):
        async with periodic_task_lock("tick_due_automations", ttl_seconds=240) as acquired:
            if not acquired:
                return []
            results = await AutomationScheduler(db).tick(enqueue_advance=True)
            return [
                {
                    "automation_id": str(item.automation_id),
                    "scheduled_occurrence": item.scheduled_occurrence,
                    "workflow_run_id": str(item.workflow_run_id) if item.workflow_run_id else None,
                    "status": item.status,
                    "error": item.error,
                }
                for item in results
            ]

    return run_async_task(
        task_name="tick_due_automations",
        queue_name="generation",
        tenant_id=None,
        entity_type="automation",
        entity_id=None,
        celery_task_id=tick_due_automations_task.request.id,
        correlation_id=tick_due_automations_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )


@_task("backend.workers.tasks.advance_workflow_run_task")
def advance_workflow_run_task(*, tenant_id: str, run_id: str) -> dict[str, str]:
    async def operation(db):
        run = await WorkflowEngine(db).advance(UUID(tenant_id), UUID(run_id))
        return {"workflow_run_id": str(run.id), "status": str(run.status)}

    return run_async_task(
        task_name="advance_workflow_run",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="workflow_run",
        entity_id=run_id,
        celery_task_id=advance_workflow_run_task.request.id,
        correlation_id=advance_workflow_run_task.request.id,
        payload=enqueue_payload(run_id=run_id),
        operation=operation,
    )


@_task("backend.workers.tasks.resume_workflow_waiting_node_task")
def resume_workflow_waiting_node_task(
    *,
    tenant_id: str,
    resume_token: str,
    outcome: str = "elapsed",
    decision: dict | None = None,
) -> dict[str, str]:
    async def operation(db):
        from backend.modules.workflows.engine_resume import resume_waiting_node

        run = await resume_waiting_node(
            WorkflowEngine(db),
            UUID(tenant_id),
            resume_token=resume_token,
            outcome=outcome,
            decision=dict(decision or {}),
            advance=True,
        )
        return {"workflow_run_id": str(run.id), "status": str(run.status)}

    return run_async_task(
        task_name="resume_workflow_waiting_node",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="workflow_node_run",
        entity_id=resume_token,
        celery_task_id=resume_workflow_waiting_node_task.request.id,
        correlation_id=resume_workflow_waiting_node_task.request.id,
        payload=enqueue_payload(resume_token=resume_token, outcome=outcome),
        operation=operation,
    )
