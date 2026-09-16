"""Celery tasks for workflow automation scheduling + durable node execution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select

from backend.modules.operations.models import TaskExecution
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.engine_node_task import execute_claimed_node_run
from backend.modules.workflows.node_recovery import recover_stale_workflow_node_runs
from backend.modules.workflows.scheduler import AutomationScheduler
from backend.modules.workflows.wait_recovery import wake_due_workflow_waits
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task
from backend.workers.task_lock import periodic_task_lock


@_task("backend.workers.tasks.tick_due_automations_task")
def tick_due_automations_task() -> list[dict[str, str | None]]:
    """Fire due schedule automations.

    Must not swallow schema errors (e.g. missing ``automations`` table). Workers
    should fail closed via schema-revision enforcement instead.
    """

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
    """Orchestration only: claim READY nodes and enqueue one-node tasks."""

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


@_task("backend.workers.tasks.execute_workflow_node_task")
def execute_workflow_node_task(
    *,
    tenant_id: str,
    workflow_run_id: str,
    node_run_id: str,
    claim_token: str,
) -> dict[str, str]:
    """Execute exactly one claimed WorkflowNodeRun."""

    celery_id = execute_workflow_node_task.request.id

    async def operation(db):
        te_id = None
        te_result = await db.execute(
            select(TaskExecution)
            .where(TaskExecution.celery_task_id == celery_id)
            .order_by(TaskExecution.created_at.desc())
            .limit(1)
        )
        te = te_result.scalar_one_or_none()
        if te is not None:
            te_id = te.id

        return await execute_claimed_node_run(
            WorkflowEngine(db),
            tenant_id=UUID(tenant_id),
            workflow_run_id=UUID(workflow_run_id),
            node_run_id=UUID(node_run_id),
            claim_token=claim_token,
            worker_task_id=celery_id,
            task_execution_id=te_id,
            enqueue_followups=True,
        )

    return run_async_task(
        task_name="execute_workflow_node",
        queue_name="generation",
        tenant_id=UUID(tenant_id),
        entity_type="workflow_node_run",
        entity_id=node_run_id,
        celery_task_id=celery_id,
        correlation_id=celery_id,
        payload=enqueue_payload(
            workflow_run_id=workflow_run_id,
            node_run_id=node_run_id,
        ),
        operation=operation,
    )


@_task("backend.workers.tasks.recover_stale_workflow_node_runs_task")
def recover_stale_workflow_node_runs_task() -> list[dict[str, Any]]:
    """Periodic crash recovery for expired node claim leases."""

    async def operation(db):
        async with periodic_task_lock(
            "recover_stale_workflow_node_runs", ttl_seconds=240
        ) as acquired:
            if not acquired:
                return []
            return await recover_stale_workflow_node_runs(db, enqueue_advance=True)

    return run_async_task(
        task_name="recover_stale_workflow_node_runs",
        queue_name="generation",
        tenant_id=None,
        entity_type="workflow_node_run",
        entity_id=None,
        celery_task_id=recover_stale_workflow_node_runs_task.request.id,
        correlation_id=recover_stale_workflow_node_runs_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )


@_task("backend.workers.tasks.wake_due_workflow_waits_task")
def wake_due_workflow_waits_task() -> list[dict[str, Any]]:
    """Postgres-owned timer scanner: claim due WorkflowWait rows and resume."""

    async def operation(db):
        async with periodic_task_lock("wake_due_workflow_waits", ttl_seconds=50) as acquired:
            if not acquired:
                return []
            return await wake_due_workflow_waits(db, enqueue_resume=True)

    return run_async_task(
        task_name="wake_due_workflow_waits",
        queue_name="generation",
        tenant_id=None,
        entity_type="workflow_wait",
        entity_id=None,
        celery_task_id=wake_due_workflow_waits_task.request.id,
        correlation_id=wake_due_workflow_waits_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )


@_task("backend.workers.tasks.resume_workflow_waiting_node_task")
def resume_workflow_waiting_node_task(
    *,
    tenant_id: str,
    resume_token: str,
    outcome: str = "elapsed",
    decision: dict[str, Any] | None = None,
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


@_task("backend.workers.tasks.process_workflow_webhook_inbox_task")
def process_workflow_webhook_inbox_task(*, inbox_id: str) -> dict[str, str]:
    """Process a workflow WebhookInbox row into an idempotent WorkflowRun."""

    async def operation(db):
        from backend.modules.workflows.webhook_ingress import process_workflow_webhook_inbox

        return await process_workflow_webhook_inbox(db, inbox_id=UUID(inbox_id))

    return run_async_task(
        task_name="process_workflow_webhook_inbox",
        queue_name="generation",
        tenant_id=None,
        entity_type="webhook_inbox",
        entity_id=inbox_id,
        celery_task_id=process_workflow_webhook_inbox_task.request.id,
        correlation_id=process_workflow_webhook_inbox_task.request.id,
        payload=enqueue_payload(inbox_id=inbox_id),
        operation=operation,
    )


@_task("backend.workers.tasks.run_workflow_retention_task")
def run_workflow_retention_task() -> dict[str, Any]:
    """Scrub/delete aged workflow payloads and TaskExecution rows (Phase 20)."""

    async def operation(db):
        async with periodic_task_lock("workflow_retention", ttl_seconds=3_500) as acquired:
            if not acquired:
                return {"enabled": False, "skipped": "lock_not_acquired"}
            from backend.modules.workflows.retention import run_workflow_retention

            return await run_workflow_retention(db)

    return run_async_task(
        task_name="run_workflow_retention",
        queue_name="generation",
        tenant_id=None,
        entity_type="workflow_retention",
        entity_id=None,
        celery_task_id=run_workflow_retention_task.request.id,
        correlation_id=run_workflow_retention_task.request.id,
        payload=enqueue_payload(),
        operation=operation,
    )
