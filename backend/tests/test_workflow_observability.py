"""Phase 16 — workflow observability (logs + domain metrics)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import structlog

from backend.core.domain_metrics import METRIC_OPERATION_TOTAL, domain_metrics, reset_domain_metrics
from backend.core.log_context import bind_log_context, drop_sensitive_log_keys
from backend.modules.workflows.observability import (
    bind_workflow_run_context,
    log_workflow_run_started,
    record_approval_wait,
    record_workflow_node_finished,
    record_workflow_run_finished,
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
        correlation_id="corr-obs-1",
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
    )
    for key, value in overrides.items():
        setattr(node, key, value)
    return node


def test_bind_workflow_context_allowlists_identity_fields() -> None:
    structlog.contextvars.clear_contextvars()
    run = _run()
    node = _node(run, attempt=2)
    bind_workflow_run_context(run, node_run=node)
    bound = structlog.contextvars.get_contextvars()
    assert bound["tenant_id"] == str(run.tenant_id)
    assert bound["correlation_id"] == "corr-obs-1"
    assert bound["workflow_run_id"] == str(run.id)
    assert bound["workflow_definition_id"] == str(run.workflow_definition_id)
    assert bound["node_id"] == "generate"
    assert bound["node_type"] == "generate_text"
    assert bound["attempt"] == "2"
    assert "resume_token" not in bound


def test_sensitive_keys_redacted_in_log_processor() -> None:
    event = drop_sensitive_log_keys(
        None,
        "info",
        {
            "oauth_token": "secret",
            "refresh_token": "secret",
            "provider_secret": "x",
            "webhook_secret": "y",
            "workflow_run_id": "ok",
        },
    )
    assert event["oauth_token"] == "[redacted]"
    assert event["refresh_token"] == "[redacted]"
    assert event["provider_secret"] == "[redacted]"
    assert event["webhook_secret"] == "[redacted]"
    assert event["workflow_run_id"] == "ok"


def test_workflow_metrics_emit_low_cardinality_attrs() -> None:
    reset_domain_metrics()
    run = _run()
    log_workflow_run_started(run)
    node = _node(run, node_type="generate_video", attempt=2)
    record_workflow_node_finished(run, node, outcome="succeeded")
    run.status = "succeeded"
    run.finished_at = datetime.now(timezone.utc)
    record_workflow_run_finished(run)
    record_approval_wait(run, _node(run, node_type="approval"), outcome="approved")

    snap = domain_metrics.snapshot()
    ops = snap["counters"].get(METRIC_OPERATION_TOTAL, [])
    operations = {row["attrs"].get("operation") for row in ops}
    assert "workflow.run" in operations
    assert "workflow.node" in operations
    assert "workflow.media" in operations
    assert "workflow.approval_wait" in operations
    for row in ops:
        assert "tenant_id" not in row["attrs"]
        assert "correlation_id" not in row["attrs"]
        assert "workflow_run_id" not in row["attrs"]


def test_bind_log_context_rejects_unknown_secretish_keys() -> None:
    structlog.contextvars.clear_contextvars()
    bind_log_context(oauth_token="nope", tenant_id=uuid4())
    bound = structlog.contextvars.get_contextvars()
    assert "oauth_token" not in bound
    assert "tenant_id" in bound
