"""Per-request context (correlation + tenant) via contextvars — no globals."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any
from uuid import UUID

import structlog

_correlation_id: ContextVar[str | None] = ContextVar("cg_correlation_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("cg_tenant_id", default=None)


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)
    if value:
        structlog.contextvars.bind_contextvars(correlation_id=value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_tenant_id(value: UUID | str | None) -> None:
    normalized = str(value) if value is not None else None
    _tenant_id.set(normalized)
    if normalized is not None:
        structlog.contextvars.bind_contextvars(tenant_id=normalized)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def clear_request_context() -> None:
    _correlation_id.set(None)
    _tenant_id.set(None)
    structlog.contextvars.clear_contextvars()


def snapshot_request_context() -> dict[str, Any]:
    return {
        "correlation_id": get_correlation_id(),
        "tenant_id": get_tenant_id(),
    }
