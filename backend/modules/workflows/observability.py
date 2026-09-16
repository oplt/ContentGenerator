"""Workflow run/node structured logging + domain metrics (Phase 16 + Phase 19).

Prometheus-facing series stay on ``cg.operation.*`` with low-cardinality attrs.
Prompt aliases (workflow_runs_total, …) map via OPERATION aliases below — never
put workflow_run_id / tenant_id / correlation_id on metric labels.
"""

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
_LLM_NODE_TYPES = frozenset(
    {
        "generate_text",
        "generate_canonical_content",
        "summarize",
        "generate_script",
        "fact_review",
        "platform_transform",
    }
)

# Prompt Phase 19 names → cg.operation.total operation=…
PHASE19_METRIC_ALIASES: dict[str, str] = {
    "workflow_runs_total": "workflow.run",
    "workflow_runs_failed": "workflow.run",  # filter outcome=failed
    "workflow_run_duration": "workflow.run",
    "workflow_node_runs_total": "workflow.node",
    "workflow_node_duration": "workflow.node",
    "workflow_node_retries": "workflow.node",  # filter event=retry
    "workflow_node_claim_expirations": "workflow.node.claim_expiration",
    "workflow_node_stale_recoveries": "workflow.node.stale_recovery",
    "workflow_wait_duration": "workflow.wait",
    "workflow_approval_duration": "workflow.approval_wait",
    "workflow_scheduler_occurrences": "workflow.scheduler.occurrence",
    "workflow_scheduler_lag": "workflow.scheduler.lag",
    "workflow_publish_jobs": "workflow.publish",
    "workflow_publish_failures": "workflow.publish",  # filter outcome=failure
    "workflow_llm_calls": "workflow.llm",
    "workflow_media_generation": "workflow.media",
}


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


def bind_workflow_run_context(
    run: WorkflowRun,
    *,
    node_run: WorkflowNodeRun | None = None,
    workflow_version: int | str | None = None,
) -> None:
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
    if workflow_version is not None:
        payload["workflow_version"] = workflow_version
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
    if node_run.node_type in _LLM_NODE_TYPES:
        domain_metrics.record_workflow_llm_call(
            node_type=node_run.node_type,
            outcome=outcome,
            duration_ms=duration,
        )
    if node_run.node_type == "publish":
        if outcome == "failed":
            domain_metrics.record_workflow_publish_failure(platform="unknown")
        elif outcome in {"succeeded", "skipped"}:
            jobs = 0
            raw = (node_run.output_json or {}).get("job_ids")
            if isinstance(raw, list):
                jobs = len(raw)
            domain_metrics.record_workflow_publish_job(
                outcome="success" if outcome == "succeeded" else "skipped",
                amount=max(jobs, 1 if outcome == "succeeded" else 0),
            )
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


def record_workflow_wait_resolved(
    *,
    wait_type: str,
    outcome: str,
    created_at: datetime | None,
    resolved_at: datetime | None = None,
    tenant_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
    resume_token: str | None = None,
) -> None:
    duration = _duration_ms(created_at, resolved_at)
    domain_metrics.record_workflow_wait(
        wait_type=wait_type,
        outcome=outcome,
        duration_ms=duration,
    )
    logger.info(
        "workflow_wait_resolved",
        wait_type=wait_type,
        outcome=outcome,
        duration_ms=round(duration, 3),
        resume_token_present=bool(resume_token),
        **ids_for_logs(tenant_id=tenant_id, workflow_run_id=workflow_run_id),
    )


def record_node_claim_expiration(*, node_type: str | None = None, amount: int = 1) -> None:
    domain_metrics.record_workflow_node_claim_expiration(amount=amount)
    logger.info(
        "workflow_node_claim_expired",
        amount=amount,
        node_type=node_type,
    )


def record_node_stale_recovery(*, action: str, node_type: str | None = None) -> None:
    domain_metrics.record_workflow_node_stale_recovery(action=action)
    logger.info(
        "workflow_node_stale_recovery",
        action=action,
        node_type=node_type,
    )


def record_scheduler_tick_result(
    *,
    outcome: str,
    lag_ms: float | None = None,
    automation_id: UUID | None = None,
    workflow_run_id: UUID | None = None,
) -> None:
    domain_metrics.record_workflow_scheduler_occurrence(outcome=outcome)
    if lag_ms is not None:
        domain_metrics.record_workflow_scheduler_lag(lag_ms=lag_ms)
    logger.info(
        "workflow_scheduler_occurrence",
        outcome=outcome,
        lag_ms=round(lag_ms, 3) if lag_ms is not None else None,
        **ids_for_logs(automation_id=automation_id, workflow_run_id=workflow_run_id),
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
    workflow_version: int | str | None = None,
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
        "workflow_version": str(workflow_version) if workflow_version is not None else None,
        "automation_id": _as_str(automation_id),
        "brand_id": _as_str(brand_id),
        "node_id": node_id,
        "node_type": node_type,
        "attempt": str(attempt) if attempt is not None else None,
    }
    return {key: value for key, value in raw.items() if value}
