"""Enqueue claimed WorkflowNodeRun execution (Celery or inline for tests)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from backend.core.config import settings
from backend.modules.workflows.run_models import WorkflowNodeRun

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine


def enqueue_claimed_node(
    *,
    tenant_id: UUID,
    workflow_run_id: UUID,
    node_run: WorkflowNodeRun,
) -> None:
    """Dispatch one-node execution. Production uses Celery; tests may run inline."""
    claim_token = node_run.claim_token
    if not claim_token:
        raise ValueError("claimed node missing claim_token")

    if settings.WORKFLOW_INLINE_NODE_EXECUTION:
        # Caller (advance) drains inline after flush; nothing to enqueue.
        return

    from backend.workers.tasks import execute_workflow_node_task

    execute_workflow_node_task.delay(
        tenant_id=str(tenant_id),
        workflow_run_id=str(workflow_run_id),
        node_run_id=str(node_run.id),
        claim_token=claim_token,
    )


async def drain_inline_claimed_nodes(
    engine: WorkflowEngine,
    *,
    tenant_id: UUID,
    run_id: UUID,
    claimed: list[WorkflowNodeRun],
) -> None:
    """Execute claimed nodes one-at-a-time in-process (unit tests / sync mode)."""
    from backend.modules.workflows.engine_node_task import execute_claimed_node_run

    for node in claimed:
        if not node.claim_token:
            continue
        await execute_claimed_node_run(
            engine,
            tenant_id=tenant_id,
            workflow_run_id=run_id,
            node_run_id=node.id,
            claim_token=node.claim_token,
            worker_task_id="inline",
            task_execution_id=None,
            enqueue_followups=False,
        )
