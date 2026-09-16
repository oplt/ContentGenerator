"""Single-node execution for WorkflowEngine (extracted for line budget + Phase 15 mocks)."""

from __future__ import annotations

import uuid
from typing import Any, TYPE_CHECKING

from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.engine_fanout import (
    ensure_downstream_iteration,
    materialize_fan_out_success,
)
from backend.modules.workflows.engine_failure import persist_failure
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.engine_node_index import (
    NodeRunIndex,
    collect_upstream_outputs,
    output_storage_key,
)
from backend.modules.workflows.engine_status import as_dict
from backend.modules.workflows.engine_unlock import unlock_after_node_success
from backend.modules.workflows.graph_schema import WorkflowGraph
from backend.modules.workflows.node_claiming import build_execution_key
from backend.modules.workflows.node_retry import (
    apply_side_effect_idempotency,
    classify_error_payload,
    classify_exception,
)
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
    node_runs: NodeRunIndex | dict[str, WorkflowNodeRun],
    node_outputs: dict[str, Any],
    initial_inputs: dict[str, Any],
    task_execution_id: uuid.UUID | None = None,
) -> None:
    if node_run.status in {
        WorkflowNodeRunStatus.SUCCEEDED.value,
        WorkflowNodeRunStatus.SKIPPED.value,
        WorkflowNodeRunStatus.WAITING.value,
    }:
        return

    index: NodeRunIndex = (
        node_runs
        if isinstance(node_runs, NodeRunIndex)
        else NodeRunIndex(list(node_runs.values()))
    )
    preds = [e.source for e in graph.edges if e.target == graph_node.id]
    upstream = collect_upstream_outputs(preds, node_outputs, index)
    impl = engine.registry.get(graph_node.type, graph_node.version)
    inputs = resolve_node_inputs(
        node_type=graph_node.type,
        trigger_payload=dict(run.trigger_payload or {}),
        initial_inputs=initial_inputs,
        upstream_outputs=upstream,
        run_id=run.id,
        schema_version=int(getattr(graph, "schema_version", 1) or 1),
        graph=graph,
        graph_node=graph_node,
        node_outputs={k: dict(v) for k, v in node_outputs.items() if isinstance(v, dict)},
        input_ports=list(impl.input_ports or []),
        run_context=as_dict(run.context_snapshot),
    )
    # Fan-out body iterations carry the item on the node_run row.
    seeded = dict(node_run.input_json or {})
    if seeded:
        for key, value in seeded.items():
            if key == "upstream":
                continue
            current = inputs.get(key)
            if current in (None, "", [], {}):
                inputs[key] = value
        seeded_upstream = seeded.get("upstream")
        if isinstance(seeded_upstream, dict):
            for key, value in seeded_upstream.items():
                current = inputs.get(key)
                if current in (None, "", [], {}):
                    inputs[key] = value
    if graph_node.type == "merge":
        inputs["sources"] = [dict(row) for row in upstream if isinstance(row, dict)]

    iter_key = (node_run.iteration_key or "") or None
    if not node_run.execution_key:
        node_run.execution_key = build_execution_key(
            workflow_run_id=run.id,
            node_id=graph_node.id,
            node_version=int(graph_node.version or 1),
            iteration_key=iter_key,
        )
    inputs = apply_side_effect_idempotency(
        node_type=graph_node.type,
        inputs=inputs,
        execution_key=node_run.execution_key,
    )

    now = datetime.now(timezone.utc)
    node_run.status = WorkflowNodeRunStatus.RUNNING.value
    node_run.attempt = int(node_run.attempt or 0) + 1
    node_run.started_at = node_run.started_at or now
    node_run.input_json = inputs
    node_run.next_attempt_at = None
    if task_execution_id is not None:
        node_run.task_execution_id = task_execution_id
        existing = list(node_run.task_execution_ids or [])
        te_str = str(task_execution_id)
        if te_str not in existing:
            existing.append(te_str)
            node_run.task_execution_ids = existing
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
        if mocked is None and not type(impl).is_executable():
            status = getattr(impl, "implementation_status", "unavailable")
            status_value = status.value if hasattr(status, "value") else str(status)
            _persist_failure(
                run=run,
                node_run=node_run,
                impl=impl,
                error={
                    "code": "node_not_executable",
                    "message": (
                        f"Node '{graph_node.type}' is {status_value} and cannot execute"
                    ),
                },
                error_class="permanent",
            )
            return
        result = mocked or await impl.execute(context, typed_in, typed_cfg)
    except Exception as exc:  # noqa: BLE001 — persist failure into node/run state
        error_class = classify_exception(exc).value
        persist_failure(
            run=run,
            node_run=node_run,
            impl=impl,
            error={"code": "execute_error", "message": str(exc)},
            error_class=error_class,
        )
        return

    raw_output = dict(result.output or {})
    if result.status in {
        NodeResultStatus.SUCCEEDED,
        NodeResultStatus.SKIPPED,
        NodeResultStatus.WAITING,
    }:
        try:
            validated = impl.validate_output(raw_output)
            raw_output = validated.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 — OutputSchema violation is permanent
            _persist_failure(
                run=run,
                node_run=node_run,
                impl=impl,
                error={
                    "code": "invalid_node_output",
                    "message": str(exc),
                },
                error_class="permanent",
            )
            return

    node_run.output_json = raw_output
    node_outputs[output_storage_key(graph_node.id, node_run.iteration_key)] = raw_output
    if not (node_run.iteration_key or ""):
        node_outputs[graph_node.id] = raw_output
    now_done = datetime.now(timezone.utc)
    if result.status in {NodeResultStatus.SUCCEEDED, NodeResultStatus.SKIPPED}:
        node_run.status = (
            WorkflowNodeRunStatus.SUCCEEDED.value
            if result.status == NodeResultStatus.SUCCEEDED
            else WorkflowNodeRunStatus.SKIPPED.value
        )
        node_run.finished_at = now_done
        node_run.error_json = None
        node_run.last_error = None
        node_run.error_class = None
        node_run.next_attempt_at = None
        if graph_node.type == "fan_out" and result.status == NodeResultStatus.SUCCEEDED:
            await materialize_fan_out_success(
                engine.db,
                tenant_id=run.tenant_id,
                run=run,
                graph=graph,
                fan_out_node_id=graph_node.id,
                output=raw_output,
                node_runs=index,
            )
        elif node_run.iteration_key:
            await ensure_downstream_iteration(
                engine.db,
                tenant_id=run.tenant_id,
                run=run,
                graph=graph,
                source_node_id=graph_node.id,
                iteration_key=str(node_run.iteration_key),
                output=raw_output,
                node_runs=index,
            )
        else:
            unlock_after_node_success(
                graph_node.id,
                graph=graph,
                node_runs=index,
                output=raw_output,
            )
        record_workflow_node_finished(run, node_run, outcome=node_run.status)
    elif result.status == NodeResultStatus.WAITING:
        node_run.status = WorkflowNodeRunStatus.WAITING.value
        node_run.waiting_reason = result.waiting_reason
        node_run.resume_token = node_run.resume_token or resume_token or str(uuid.uuid4())
        node_run.finished_at = None
        node_run.last_error = None
        node_run.error_class = None
        node_run.next_attempt_at = None
        from backend.modules.workflows.wait_persist import persist_waiting_node

        await persist_waiting_node(
            engine.db,
            run=run,
            node_run=node_run,
            output=raw_output,
            waiting_reason=result.waiting_reason,
        )
        record_workflow_node_finished(run, node_run, outcome="waiting")
    else:
        payload = dict(result.error or {"code": "node_failed"})
        error_class = classify_error_payload(payload).value
        persist_failure(
            run=run,
            node_run=node_run,
            impl=impl,
            error=payload,
            error_class=error_class,
        )
