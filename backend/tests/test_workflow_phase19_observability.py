"""Phase 19 — workflow observability extensions (metrics + log identity)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import structlog

from backend.core.domain_metrics import METRIC_OPERATION_DURATION, METRIC_OPERATION_TOTAL
from backend.core.domain_metrics import domain_metrics, reset_domain_metrics
from backend.core.log_context import bind_log_context
from backend.modules.workflows.observability import (
    PHASE19_METRIC_ALIASES,
    bind_workflow_run_context,
    log_workflow_run_started,
    record_node_claim_expiration,
    record_node_stale_recovery,
    record_scheduler_tick_result,
    record_workflow_node_finished,
    record_workflow_run_finished,
    record_workflow_wait_resolved,
)
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun


def _run(**overrides: object) -> WorkflowRun:
    now = datetime.now(timezone.utc)
    run = WorkflowRun(
        id=uuid4(),
        tenant_id=uuid4(),
        workflow_definition_id=uuid4(),
        workflow_version_id=uuid4(),
        automation_id=uuid4(),
        brand_id=uuid4(),
        trigger_type="manual",
        trigger_payload={},
        status="running",
        context_snapshot={},
        started_at=now,
        correlation_id="corr-p19",
    )
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def _node(run: WorkflowRun, **overrides: object) -> WorkflowNodeRun:
    now = datetime.now(timezone.utc)
    node = WorkflowNodeRun(
        id=uuid4(),
        tenant_id=run.tenant_id,
        workflow_run_id=run.id,
        node_id="generate",
        node_type="generate_text",
        node_version=1,
        status="succeeded",
        attempt=1,
        started_at=now,
        finished_at=now,
        output_json={},
    )
    for key, value in overrides.items():
        setattr(node, key, value)
    return node


def _ops() -> list[dict]:
    return domain_metrics.snapshot()["counters"].get(METRIC_OPERATION_TOTAL, [])


def _hist() -> list[dict]:
    return domain_metrics.snapshot()["histograms"].get(METRIC_OPERATION_DURATION, [])


def test_phase19_aliases_cover_prompt_metric_names() -> None:
    required = {
        "workflow_runs_total",
        "workflow_runs_failed",
        "workflow_run_duration",
        "workflow_node_runs_total",
        "workflow_node_duration",
        "workflow_node_retries",
        "workflow_node_claim_expirations",
        "workflow_node_stale_recoveries",
        "workflow_wait_duration",
        "workflow_approval_duration",
        "workflow_scheduler_occurrences",
        "workflow_scheduler_lag",
        "workflow_publish_jobs",
        "workflow_publish_failures",
        "workflow_llm_calls",
        "workflow_media_generation",
    }
    assert required <= set(PHASE19_METRIC_ALIASES)


def test_bind_includes_workflow_version_for_logs_not_metrics() -> None:
    structlog.contextvars.clear_contextvars()
    run = _run()
    bind_workflow_run_context(run, workflow_version=3)
    bound = structlog.contextvars.get_contextvars()
    assert bound["workflow_definition_id"] == str(run.workflow_definition_id)
    assert bound["workflow_version"] == "3"
    assert bound["automation_id"] == str(run.automation_id)
    assert "workflow_run_id" in bound


def test_phase19_metrics_emit_without_high_cardinality_labels() -> None:
    reset_domain_metrics()
    run = _run()
    log_workflow_run_started(run)

    publish = _node(
        run,
        node_type="publish",
        node_id="publish",
        output_json={"job_ids": [str(uuid4()), str(uuid4())]},
    )
    record_workflow_node_finished(run, publish, outcome="succeeded")

    llm = _node(run, node_type="generate_text", attempt=2)
    record_workflow_node_finished(run, llm, outcome="succeeded")

    media = _node(run, node_type="generate_chess_video", node_id="chess")
    record_workflow_node_finished(run, media, outcome="succeeded")

    record_node_claim_expiration(node_type="generate_text")
    record_node_stale_recovery(action="requeued", node_type="generate_text")
    record_workflow_wait_resolved(
        wait_type="delay",
        outcome="elapsed",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        tenant_id=run.tenant_id,
        workflow_run_id=run.id,
    )
    record_scheduler_tick_result(
        outcome="started",
        lag_ms=1500.0,
        automation_id=run.automation_id,
        workflow_run_id=run.id,
    )

    run.status = "failed"
    run.finished_at = datetime.now(timezone.utc)
    record_workflow_run_finished(run)

    ops = {row["attrs"].get("operation") for row in _ops()}
    assert "workflow.run" in ops
    assert "workflow.node" in ops
    assert "workflow.publish" in ops
    assert "workflow.llm" in ops
    assert "workflow.media" in ops
    assert "workflow.node.claim_expiration" in ops
    assert "workflow.node.stale_recovery" in ops
    assert "workflow.wait" in ops
    assert "workflow.scheduler.occurrence" in ops

    hist_ops = {row["attrs"].get("operation") for row in _hist()}
    assert "workflow.scheduler.lag" in hist_ops
    assert "workflow.wait" in hist_ops

    for row in _ops() + _hist():
        attrs = row["attrs"]
        assert "tenant_id" not in attrs
        assert "workflow_run_id" not in attrs
        assert "correlation_id" not in attrs
        assert "automation_id" not in attrs


def test_publish_failure_and_retry_event() -> None:
    reset_domain_metrics()
    run = _run()
    failed = _node(run, node_type="publish", node_id="publish")
    record_workflow_node_finished(run, failed, outcome="failed")
    retried = _node(run, node_type="summarize", attempt=3)
    record_workflow_node_finished(run, retried, outcome="succeeded")

    publish_rows = [
        row
        for row in _ops()
        if row["attrs"].get("operation") == "workflow.publish"
        and row["attrs"].get("outcome") == "failure"
    ]
    assert publish_rows
    retry_rows = [
        row
        for row in _ops()
        if row["attrs"].get("operation") == "workflow.node"
        and row["attrs"].get("event") == "retry"
    ]
    assert retry_rows


def test_bind_log_context_allows_workflow_version() -> None:
    structlog.contextvars.clear_contextvars()
    bind_log_context(workflow_version=2, workflow_definition_id=uuid4())
    bound = structlog.contextvars.get_contextvars()
    assert bound["workflow_version"] == "2"
