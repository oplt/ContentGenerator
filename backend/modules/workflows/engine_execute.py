"""Single-node execution for WorkflowEngine (extracted for line budget + Phase 15 mocks)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.engine_status import as_dict
from backend.modules.workflows.engine_unlock import unlock_after_node_success
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.nodes.base import NodeResultStatus
from backend.modules.workflows.observability import (
    bind_workflow_run_context,
    record_workflow_node_finished,
)
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus, WorkflowRun
from backend.modules.workflows.testing_support import maybe_mock_node_result

if TYPE_CHECKING:
    from backend.modules.workflows.engine import WorkflowEngine


async def execute_ready_node(
    engine: WorkflowEngine,
    *,
    run: WorkflowRun,
    graph_node: Any,
    node_run: WorkflowNodeRun,
    graph: WorkflowGraph,
    node_runs: dict[str, WorkflowNodeRun],
    node_outputs: dict[str, Any],
    initial_inputs: dict[str, Any],
) -> None:
    if node_run.status in {
        WorkflowNodeRunStatus.SUCCEEDED.value,
        WorkflowNodeRunStatus.SKIPPED.value,
        WorkflowNodeRunStatus.WAITING.value,
    }:
        return

    preds = [e.source for e in graph.edges if e.target == graph_node.id]
    upstream = [dict(node_outputs.get(pid) or {}) for pid in preds]
    inputs = resolve_node_inputs(
        node_type=graph_node.type,
        trigger_payload=dict(run.trigger_payload or {}),
        initial_inputs=initial_inputs,
        upstream_outputs=upstream,
        run_id=run.id,
    )

    impl = engine.registry.get(graph_node.type, graph_node.version)
    now = datetime.now(timezone.utc)
    node_run.status = WorkflowNodeRunStatus.RUNNING.value
    node_run.attempt = int(node_run.attempt or 0) + 1
    node_run.started_at = node_run.started_at or now
    node_run.input_json = inputs
    resume_token = node_run.resume_token
    if impl.may_pause and not resume_token:
        resume_token = str(uuid.uuid4())
        node_run.resume_token = resume_token
    await engine.db.flush()
    bind_workflow_run_context(run, node_run=node_run)

    context = build_node_context(
        tenant_id=run.tenant_id,
        db=engine.db,
        correlation_id=run.correlation_id,
        workflow_run_id=run.id,
        automation_id=run.automation_id,
        brand_id=run.brand_id,
        node_id=graph_node.id,
        node_run_id=node_run.id,
        resume_token=resume_token,
        snapshot=dict(run.context_snapshot or {}),
    )
    try:
        typed_in = impl.validate_inputs(inputs)
        snapshot_cfg = as_dict(as_dict(run.context_snapshot).get("resolved_node_configs"))
        resolved_cfg = snapshot_cfg.get(graph_node.id)
        typed_cfg = impl.validate_config(
            resolved_cfg if isinstance(resolved_cfg, dict) else (graph_node.config or {})
        )
        mocked = maybe_mock_node_result(
            node_type=graph_node.type,
            inputs=inputs,
            snapshot=dict(run.context_snapshot or {}),
        )
        result = mocked or await impl.execute(context, typed_in, typed_cfg)
    except Exception as exc:  # noqa: BLE001 — persist failure into node/run state
        node_run.status = WorkflowNodeRunStatus.FAILED.value
        node_run.error_json = {"code": "execute_error", "message": str(exc)}
        node_run.finished_at = datetime.now(timezone.utc)
        record_workflow_node_finished(run, node_run, outcome="failed")
        return

    node_run.output_json = dict(result.output or {})
    node_outputs[graph_node.id] = dict(result.output or {})
    now_done = datetime.now(timezone.utc)
    if result.status in {NodeResultStatus.SUCCEEDED, NodeResultStatus.SKIPPED}:
        node_run.status = (
            WorkflowNodeRunStatus.SUCCEEDED.value
            if result.status == NodeResultStatus.SUCCEEDED
            else WorkflowNodeRunStatus.SKIPPED.value
        )
        node_run.finished_at = now_done
        node_run.error_json = None
        unlock_after_node_success(
            graph_node.id,
            graph=graph,
            node_runs=node_runs,
            output=dict(result.output or {}),
        )
        record_workflow_node_finished(run, node_run, outcome=node_run.status)
    elif result.status == NodeResultStatus.WAITING:
        node_run.status = WorkflowNodeRunStatus.WAITING.value
        node_run.waiting_reason = result.waiting_reason
        node_run.resume_token = node_run.resume_token or resume_token or str(uuid.uuid4())
        node_run.finished_at = None
        record_workflow_node_finished(run, node_run, outcome="waiting")
    else:
        node_run.status = WorkflowNodeRunStatus.FAILED.value
        node_run.error_json = dict(result.error or {"code": "node_failed"})
        node_run.finished_at = now_done
        record_workflow_node_finished(run, node_run, outcome="failed")
