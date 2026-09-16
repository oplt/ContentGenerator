"""Workflow node failure and retry state transitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.modules.workflows.node_retry import error_message, next_attempt_at_for, should_retry
from backend.modules.workflows.nodes.base import RetryPolicyDefaults, WorkflowNode
from backend.modules.workflows.observability import record_workflow_node_finished
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowNodeRunStatus, WorkflowRun


def persist_failure(
    *,
    run: WorkflowRun,
    node_run: WorkflowNodeRun,
    impl: WorkflowNode[Any, Any, Any],
    error: dict[str, Any],
    error_class: str,
) -> None:
    """Mark a node failed or schedule its next durable retry."""
    now = datetime.now(timezone.utc)
    policy: RetryPolicyDefaults = impl.retry_policy
    attempt = int(node_run.attempt or 0)
    message = error_message(error)
    node_run.last_error = message
    node_run.error_class = error_class
    node_run.error_json = {**error, "error_class": error_class}

    if should_retry(error_class=error_class, attempt=attempt, policy=policy):
        node_run.status = WorkflowNodeRunStatus.READY.value
        node_run.next_attempt_at = next_attempt_at_for(attempt, policy, now=now)
        node_run.finished_at = None
        record_workflow_node_finished(run, node_run, outcome="retry_scheduled")
        return

    node_run.status = WorkflowNodeRunStatus.FAILED.value
    node_run.finished_at = now
    node_run.next_attempt_at = None
    record_workflow_node_finished(run, node_run, outcome="failed")
