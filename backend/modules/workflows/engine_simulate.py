"""Approval auto-simulate loop for dry runs (Phase 15)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from backend.modules.workflows.run_models import WorkflowNodeRunStatus, WorkflowRunStatus

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine
    from backend.modules.workflows.run_models import WorkflowRun


async def auto_simulate_approvals(
    engine: WorkflowEngine,
    tenant_id: UUID,
    run_id: UUID,
    *,
    max_hops: int = 8,
) -> WorkflowRun:
    """Resume WAITING approval nodes with outcome=approved until run leaves waiting."""
    from backend.modules.workflows.engine_resume import resume_waiting_node

    run = await engine.runs.get_run(tenant_id, run_id)
    if run is None:
        raise ValueError(f"Workflow run not found: {run_id}")

    for _ in range(max_hops):
        if run.status != WorkflowRunStatus.WAITING.value:
            return run
        nodes = await engine.runs.list_node_runs(tenant_id, run.id)
        waiting = next(
            (
                node
                for node in nodes
                if node.status == WorkflowNodeRunStatus.WAITING.value
                and node.resume_token
                and node.node_type == "approval"
            ),
            None,
        )
        if waiting is None or not waiting.resume_token:
            return run
        run = await resume_waiting_node(
            engine,
            tenant_id,
            resume_token=waiting.resume_token,
            outcome="approved",
            decision={"simulated": True, "source": "dry_run"},
            advance=True,
        )
    return run
