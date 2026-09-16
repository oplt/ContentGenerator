"""Typed workflow node retry classification and backoff (Phase 2)."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from backend.core.config import settings
from backend.modules.workflows.nodes.base import RetryPolicyDefaults


class ErrorClass(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    VALIDATION = "validation"
    PERMANENT = "permanent"
    AUTHENTICATION = "authentication"
    POLICY = "policy"


# Never retry these unless explicitly listed in retry_on.
NON_RETRYABLE_BY_DEFAULT = frozenset(
    {
        ErrorClass.VALIDATION.value,
        ErrorClass.PERMANENT.value,
        ErrorClass.AUTHENTICATION.value,
        ErrorClass.POLICY.value,
    }
)

_DEFAULT_RETRY_ON = (
    ErrorClass.TRANSIENT.value,
    ErrorClass.RATE_LIMITED.value,
    ErrorClass.TIMEOUT.value,
    ErrorClass.PROVIDER_UNAVAILABLE.value,
)


def compute_backoff_seconds(
    attempt: int,
    policy: RetryPolicyDefaults,
    *,
    jitter_ratio: float = 0.2,
) -> float:
    """Exponential backoff with bounded jitter: min(max, base * 2^(attempt-1)) ± jitter."""
    attempt = max(1, int(attempt))
    base = float(policy.backoff_seconds or 0.0)
    max_backoff = float(getattr(policy, "max_backoff_seconds", 300.0) or 300.0)
    raw = min(max_backoff, base * (2 ** (attempt - 1)))
    if raw <= 0:
        return 0.0
    jitter = raw * max(0.0, min(1.0, jitter_ratio)) * random.uniform(-1.0, 1.0)
    return float(max(0.0, raw + jitter))


def next_attempt_at_for(
    attempt: int,
    policy: RetryPolicyDefaults,
    *,
    now: datetime | None = None,
) -> datetime:
    now = now or datetime.now(timezone.utc)
    if settings.WORKFLOW_INLINE_NODE_EXECUTION:
        return now
    delay = compute_backoff_seconds(attempt, policy)
    return now + timedelta(seconds=delay)


def should_retry(
    *,
    error_class: str,
    attempt: int,
    policy: RetryPolicyDefaults,
) -> bool:
    if attempt >= int(policy.max_attempts):
        return False
    retry_on = {str(item).lower() for item in (policy.retry_on or list(_DEFAULT_RETRY_ON))}
    normalized = str(error_class or ErrorClass.PERMANENT.value).lower()
    if normalized in NON_RETRYABLE_BY_DEFAULT and normalized not in retry_on:
        return False
    return normalized in retry_on


def classify_exception(exc: BaseException) -> ErrorClass:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, (TimeoutError,)):
        return ErrorClass.TIMEOUT
    if "timeout" in name or "timeout" in message:
        return ErrorClass.TIMEOUT
    if "rate" in message and "limit" in message:
        return ErrorClass.RATE_LIMITED
    if "429" in message:
        return ErrorClass.RATE_LIMITED
    if any(token in message for token in ("401", "403", "unauthorized", "forbidden", "auth")):
        return ErrorClass.AUTHENTICATION
    if any(token in message for token in ("validation", "invalid", "schema", "422")):
        return ErrorClass.VALIDATION
    if any(token in message for token in ("policy", "blocked", "denied")):
        return ErrorClass.POLICY
    if any(
        token in name or token in message
        for token in ("connection", "unavailable", "connect", "dns", "network")
    ):
        return ErrorClass.PROVIDER_UNAVAILABLE
    if isinstance(exc, (ConnectionError, OSError)):
        return ErrorClass.PROVIDER_UNAVAILABLE
    return ErrorClass.TRANSIENT


_CODE_MAP: dict[str, ErrorClass] = {
    "transient": ErrorClass.TRANSIENT,
    "timeout": ErrorClass.TIMEOUT,
    "rate_limited": ErrorClass.RATE_LIMITED,
    "rate_limit": ErrorClass.RATE_LIMITED,
    "provider_unavailable": ErrorClass.PROVIDER_UNAVAILABLE,
    "unavailable": ErrorClass.PROVIDER_UNAVAILABLE,
    "validation": ErrorClass.VALIDATION,
    "invalid": ErrorClass.VALIDATION,
    "invalid_node_output": ErrorClass.PERMANENT,
    "authentication": ErrorClass.AUTHENTICATION,
    "auth": ErrorClass.AUTHENTICATION,
    "policy": ErrorClass.POLICY,
    "permanent": ErrorClass.PERMANENT,
    "missing_db": ErrorClass.PERMANENT,
    "missing_graph_node": ErrorClass.PERMANENT,
    "execute_error": ErrorClass.TRANSIENT,
    "node_failed": ErrorClass.TRANSIENT,
    "claim_lease_expired": ErrorClass.TRANSIENT,
}


def classify_error_payload(error: dict[str, Any] | None) -> ErrorClass:
    if not error:
        return ErrorClass.PERMANENT
    code = str(error.get("code") or error.get("error_class") or "").lower()
    if code in _CODE_MAP:
        return _CODE_MAP[code]
    if "error_class" in error:
        try:
            return ErrorClass(str(error["error_class"]).lower())
        except ValueError:
            pass
    message = str(error.get("message") or "")
    return classify_exception(RuntimeError(message))


def error_message(error: dict[str, Any] | None, *, fallback: str = "node failed") -> str:
    if not error:
        return fallback
    msg = error.get("message") or error.get("code") or fallback
    text = str(msg)
    return text if len(text) <= 2000 else text[:2000]


def schedule_run_advance(*, tenant_id: UUID, run_id: UUID, delay_seconds: float) -> None:
    """Enqueue orchestration after backoff (skipped when inline tests drain immediately)."""
    if settings.WORKFLOW_INLINE_NODE_EXECUTION:
        return
    from backend.workers.tasks import advance_workflow_run_task

    countdown = max(1, int(math.ceil(delay_seconds))) if delay_seconds > 0 else 0
    advance_workflow_run_task.apply_async(
        kwargs={"tenant_id": str(tenant_id), "run_id": str(run_id)},
        countdown=countdown,
    )


def apply_side_effect_idempotency(
    *,
    node_type: str,
    inputs: dict[str, Any],
    execution_key: str | None,
) -> dict[str, Any]:
    """Ensure publish (and similar) use a deterministic idempotency key on redelivery."""
    merged = dict(inputs)
    key = execution_key or merged.get("idempotency_key")
    if node_type == "publish" and key and not merged.get("idempotency_key"):
        # Publishing idempotency keys require min length 8.
        merged["idempotency_key"] = str(key) if len(str(key)) >= 8 else f"wf-{key}"
    return merged
