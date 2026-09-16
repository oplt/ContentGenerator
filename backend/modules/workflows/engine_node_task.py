"""Single claimed-node execution entry (Celery worker + inline drain)."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException

from backend.modules.workflows.engine_execute import execute_ready_node
from backend.modules.workflows.engine_status import as_dict, finalize_run_status
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.node_retry import compute_backoff_seconds, schedule_run_advance
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRunStatus,
)
from backend.modules.workflows import run_repository as node_claims
from backend.modules.workflows.workflow_cancellation import (
    abort_node_for_cancellation,
    should_abort_node,
)

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine


async def execute_claimed_node_run(
    engine: WorkflowEngine,
    *,
    tenant_id: UUID,
    workflow_run_id: UUID,
    node_run_id: UUID,
    claim_token: str,
    worker_task_id: str | None = None,
    task_execution_id: UUID | None = None,
    enqueue_followups: bool = True,
) -> dict[str, str]:
    """Execute exactly one claimed node; optionally enqueue newly-ready nodes."""
    run = await engine.runs.get_run(tenant_id, workflow_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status in {
        WorkflowRunStatus.SUCCEEDED.value,
        WorkflowRunStatus.FAILED.value,
        WorkflowRunStatus.CANCELLED.value,
    }:
        pending = await engine.db.get(WorkflowNodeRun, node_run_id)
        if (
            pending is not None
            and pending.tenant_id == tenant_id
            and pending.status
            in {
                WorkflowNodeRunStatus.QUEUED.value,
                WorkflowNodeRunStatus.RUNNING.value,
                WorkflowNodeRunStatus.READY.value,
            }
        ):
            await abort_node_for_cancellation(
                engine,
                tenant_id=tenant_id,
                node=pending,
                claim_token=claim_token if pending.claim_token == claim_token else None,
            )
            await engine.db.flush()
        return {"workflow_run_id": str(run.id), "status": str(run.status), "skipped": "terminal"}

    node = await node_claims.begin_node_execution(
        engine.db,
        tenant_id=tenant_id,
        node_run_id=node_run_id,
        claim_token=claim_token,
        worker_task_id=worker_task_id,
        task_execution_id=task_execution_id,
    )
    if node is None:
        return {
            "workflow_run_id": str(workflow_run_id),
            "status": "claim_rejected",
            "node_run_id": str(node_run_id),
        }

    refreshed = await engine.runs.get_run(tenant_id, workflow_run_id)
    if refreshed is not None:
        run = refreshed
    if should_abort_node(node, run):
        await abort_node_for_cancellation(
            engine, tenant_id=tenant_id, node=node, claim_token=claim_token
        )
        finalize_run_status(run, await engine._node_map(tenant_id, run.id))
        await engine.db.flush()
        return {
            "workflow_run_id": str(run.id),
            "status": str(run.status),
            "node_run_id": str(node.id),
            "node_status": WorkflowNodeRunStatus.CANCELLED.value,
            "skipped": "cancelled",
        }

    version = await engine.versions.get_version(tenant_id, run.workflow_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Workflow version not found")
    graph = WorkflowGraph.model_validate(version.graph_json)
    graph_nodes = {n.id: n for n in graph.nodes}
    graph_node = graph_nodes.get(node.node_id)
    if graph_node is None:
        await node_claims.fail_node(
            engine.db,
            tenant_id=tenant_id,
            node_run_id=node.id,
            claim_token=claim_token,
            error={"code": "missing_graph_node", "message": f"node {node.node_id} missing"},
            error_class="permanent",
            last_error=f"node {node.node_id} missing",
        )
        node_runs = await engine._node_map(tenant_id, run.id)
        finalize_run_status(run, node_runs)
        await engine.db.flush()
        return {"workflow_run_id": str(run.id), "status": str(run.status)}

    node_runs = await engine._node_map(tenant_id, run.id)
    snapshot = as_dict(run.context_snapshot)
    node_outputs: dict[str, Any] = as_dict(snapshot.get("node_outputs"))
    initial_inputs = as_dict(snapshot.get("initial_inputs"))

    await execute_ready_node(
        engine,
        run=run,
        graph_node=graph_node,
        node_run=node_runs.by_uuid.get(node.id, node),
        graph=graph,
        node_runs=node_runs,
        node_outputs=node_outputs,
        initial_inputs=initial_inputs,
        task_execution_id=task_execution_id,
    )

    finished = node_runs.by_uuid.get(node.id, node)
    # Cancel race: irreversible SUCCEEDED wins; otherwise honor cancellation.
    await engine.db.refresh(run)
    if (
        finished.status != WorkflowNodeRunStatus.SUCCEEDED.value
        and should_abort_node(finished, run)
    ):
        finished.cancellation_requested = True
        finished.status = WorkflowNodeRunStatus.CANCELLED.value
        finished.error_json = finished.error_json or {
            "code": "cancelled",
            "message": "cancelled",
        }

    await node_claims.complete_node(
        engine.db,
        tenant_id=tenant_id,
        node_run_id=finished.id,
        claim_token=claim_token,
    )

    snapshot["node_outputs"] = node_outputs
    run.context_snapshot = snapshot
    finalize_run_status(run, node_runs)
    from backend.modules.workflows.occurrence_sync import sync_occurrence_for_run

    await sync_occurrence_for_run(engine.db, run)
    await engine.db.flush()

    if (
        finished.status == WorkflowNodeRunStatus.READY.value
        and finished.next_attempt_at is not None
        and enqueue_followups
    ):
        try:
            impl = engine.registry.get(finished.node_type, int(finished.node_version or 1))
            delay = compute_backoff_seconds(int(finished.attempt or 1), impl.retry_policy)
        except Exception:  # noqa: BLE001
            delay = 2.0
        schedule_run_advance(tenant_id=tenant_id, run_id=run.id, delay_seconds=delay)
        from backend.core.config import settings

        if settings.WORKFLOW_INLINE_NODE_EXECUTION:
            await engine.advance(tenant_id, run.id)
    elif enqueue_followups and run.status == WorkflowRunStatus.RUNNING.value:
        await engine.advance(tenant_id, run.id)

    return {
        "workflow_run_id": str(run.id),
        "status": str(run.status),
        "node_run_id": str(finished.id),
        "node_status": str(finished.status),
    }
