"""Structured log context helpers + secret field redaction."""

from __future__ import annotations

from typing import Any, MutableMapping
from uuid import UUID

import structlog

# Fields permitted in workflow/request logs (never secrets).
_CONTEXT_KEYS = frozenset(
    {
        "correlation_id",
        "tenant_id",
        "job_id",
        "source_id",
        "publishing_job_id",
        "provider",
        "stage",
        "duration_ms",
        "workflow_run_id",
        "workflow_definition_id",
        "workflow_version_id",
        "automation_id",
        "brand_id",
        "node_id",
        "node_type",
        "attempt",
    }
)

_SENSITIVE_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "access_key",
)


def _stringify(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, float):
        return str(round(value, 3))
    return str(value)


def bind_log_context(**kwargs: Any) -> None:
    """Bind low-risk workflow ids into structlog contextvars."""
    payload: dict[str, Any] = {}
    for key, value in kwargs.items():
        if key not in _CONTEXT_KEYS or value is None:
            continue
        payload[key] = _stringify(value)
    if payload:
        structlog.contextvars.bind_contextvars(**payload)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()


def drop_sensitive_log_keys(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor: redact passwords/tokens/API keys/authorization."""
    for key in list(event_dict):
        lowered = str(key).lower()
        if any(frag in lowered for frag in _SENSITIVE_KEY_FRAGMENTS):
            event_dict[key] = "[redacted]"
    return event_dict
