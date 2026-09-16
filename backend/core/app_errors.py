"""Canonical structured application error logging (one event per failure)."""

from __future__ import annotations

import re
from typing import Any

import structlog
from starlette.requests import Request

from backend.core.request_context import get_correlation_id, get_tenant_id

logger = structlog.get_logger("backend.app_error")

_STATE_FLAG = "app_error_logged"

# Strip common credential / SQL bind leakage from exception text.
_SECRET_PATTERNS = (
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
)


def sanitize_error_text(value: str, *, limit: int = 500) -> str:
    text = value.replace("\x00", "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    # Avoid dumping full SQL with bound params from DBAPI messages.
    upper = text.upper()
    if "DETAIL:" in upper or "[SQL:" in text or "params:" in text.lower():
        text = text.split("\n", 1)[0]
    return text[:limit]


def _correlation_id(request: Request | None) -> str | None:
    if request is not None:
        value = getattr(request.state, "correlation_id", None)
        if value:
            return str(value)
    return get_correlation_id()


def _tenant_id(request: Request | None) -> str | None:
    if request is not None:
        value = getattr(request.state, "tenant_id", None)
        if value is not None:
            return str(value)
    return get_tenant_id()


def was_application_error_logged(request: Request | None) -> bool:
    if request is None:
        return False
    return bool(getattr(request.state, _STATE_FLAG, False))


def mark_application_error_logged(request: Request | None) -> None:
    if request is not None:
        setattr(request.state, _STATE_FLAG, True)


def log_application_error(
    exc: BaseException,
    *,
    request: Request | None = None,
    method: str | None = None,
    route: str | None = None,
    path: str | None = None,
    status_code: int = 500,
    error_code: str = "internal_error",
    duration_ms: float | None = None,
    include_traceback: bool = True,
    force: bool = False,
    **extra: Any,
) -> None:
    """
    Emit a single structured ``application_error`` event.

    Subsequent callers for the same request should pass the same ``request`` so
    duplicates are skipped (unless ``force=True``).
    """
    if not force and was_application_error_logged(request):
        return

    correlation_id = _correlation_id(request)
    tenant_id = _tenant_id(request)
    if request is not None:
        method = method or request.method
        path = path or request.url.path

    payload: dict[str, Any] = {
        "correlation_id": correlation_id,
        "request_id": correlation_id,
        "tenant_id": tenant_id,
        "method": method,
        "route": route,
        "path": path,
        "status_code": status_code,
        "error_type": type(exc).__name__,
        "error_code": error_code,
        "error_message": sanitize_error_text(str(exc)),
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    for key, value in extra.items():
        if value is not None:
            payload[key] = value

    mark_application_error_logged(request)

    if include_traceback:
        logger.exception("application_error", **payload)
    else:
        logger.error("application_error", **payload)
