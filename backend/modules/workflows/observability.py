"""Workflow run/node structured logging + domain metrics (Phase 16)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from backend.core.domain_metrics import domain_metrics
from backend.core.log_context import bind_log_context
from backend.core.logging import get_logger
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun

logger = get_logger(__name__)

_MEDIA_NODE_TYPES = frozenset(
    {
        "generate_image",
        "generate_video",
        "generate_tts",
        "generate_chess_video",
    }
)


def _as_str(value: UUID | str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _duration_ms(started: datetime | None, finished: datetime | None = None) -> float:
    if started is None:
        return 0.0
    end = finished or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0.0, (end - started).total_seconds() * 1000.0)


def bind_workflow_run_context(run: WorkflowRun, *, node_run: WorkflowNodeRun | None = None) -> None:
    """Bind identity fields for logs/spans — never secrets/tokens."""
    payload: dict[str, Any] = {
        "tenant_id": run.tenant_id,
        "correlation_id": run.correlation_id,
        "workflow_run_id": run.id,
        "workflow_definition_id": run.workflow_definition_id,
        "workflow_version_id": run.workflow_version_id,
        "automation_id": run.automation_id,
        "brand_id": run.brand_id,
    }
    if node_run is not None:
        payload.update(
            {
                "node_id": node_run.node_id,
                "node_type": node_run.node_type,
                "attempt": node_run.attempt,
            }
        )
    bind_log_context(**payload)


def log_workflow_run_started(run: WorkflowRun) -> None:
    bind_workflow_run_context(run)
    logger.info(
        "workflow_run_started",
        trigger_type=run.trigger_type,
        status=run.status,
    )
    domain_metrics.record_workflow_run(outcome="started", duration_ms=0.0)


def record_workflow_run_finished(run: WorkflowRun) -> None:
    if run.finished_at is None:
        return
    bind_workflow_run_context(run)
    outcome = run.status
    duration = _duration_ms(run.started_at, run.finished_at)
    error_class = None
    if outcome == "failed":
        error_class = "workflow_failed"
    domain_metrics.record_workflow_run(
        outcome=outcome,
        duration_ms=duration,
        error_class=error_class,
    )
    logger.info(
        "workflow_run_finished",
        status=run.status,
        duration_ms=round(duration, 3),
        error_message=run.error_message,
    )


def record_workflow_node_finished(
    run: WorkflowRun,
    node_run: WorkflowNodeRun,
    *,
    outcome: str,
) -> None:
    bind_workflow_run_context(run, node_run=node_run)
    duration = _duration_ms(node_run.started_at, node_run.finished_at)
    event = "retry" if int(node_run.attempt or 0) > 1 else None
    domain_metrics.record_workflow_node(
        node_type=node_run.node_type,
        outcome=outcome,
        duration_ms=duration,
        event=event,
    )
    if node_run.node_type in _MEDIA_NODE_TYPES:
        domain_metrics.record_workflow_media(
            node_type=node_run.node_type,
            outcome=outcome,
            duration_ms=duration,
        )
    if node_run.node_type == "publish" and outcome == "failed":
        domain_metrics.record_workflow_publish_failure(platform="unknown")
    logger.info(
        "workflow_node_finished",
        status=outcome,
        duration_ms=round(duration, 3),
        waiting_reason=node_run.waiting_reason,
    )


def record_approval_wait(run: WorkflowRun, node_run: WorkflowNodeRun, *, outcome: str) -> None:
    bind_workflow_run_context(run, node_run=node_run)
    duration = _duration_ms(node_run.started_at, node_run.finished_at)
    domain_metrics.record_workflow_approval_wait(duration_ms=duration, outcome=outcome)
    logger.info(
        "workflow_approval_wait_finished",
        outcome=outcome,
        duration_ms=round(duration, 3),
    )


def safe_log_fields(**kwargs: Any) -> dict[str, Any]:
    """Drop None values; callers still must avoid secrets."""
    return {key: value for key, value in kwargs.items() if value is not None}


def ids_for_logs(
    *,
    tenant_id: UUID | None = None,
    correlation_id: str | None = None,
    workflow_run_id: UUID | None = None,
    workflow_definition_id: UUID | None = None,
    workflow_version_id: UUID | None = None,
    automation_id: UUID | None = None,
    brand_id: UUID | None = None,
    node_id: str | None = None,
    node_type: str | None = None,
    attempt: int | None = None,
) -> dict[str, str]:
    raw = {
        "tenant_id": _as_str(tenant_id),
        "correlation_id": correlation_id,
        "workflow_run_id": _as_str(workflow_run_id),
        "workflow_definition_id": _as_str(workflow_definition_id),
        "workflow_version_id": _as_str(workflow_version_id),
        "automation_id": _as_str(automation_id),
        "brand_id": _as_str(brand_id),
        "node_id": node_id,
        "node_type": node_type,
        "attempt": str(attempt) if attempt is not None else None,
    }
    return {key: value for key, value in raw.items() if value}
