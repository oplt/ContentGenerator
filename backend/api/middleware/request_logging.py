from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.app_errors import log_application_error, was_application_error_logged
from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger
from backend.core.request_context import get_tenant_id

logger = get_logger("backend.request")

_QUIET_SUCCESS_ROUTES = {
    "/metrics",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/health/metrics",
    "/api/v1/health/web-vitals",
}

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path[:64]
    return _UUID_RE.sub("{id}", request.url.path)[:64]


def _correlation_id(request: Request) -> str:
    """Prefer request.state (set by CorrelationIdMiddleware); never invent here."""
    value = getattr(request.state, "correlation_id", None)
    return str(value) if value else "n/a"


def _tenant_id(request: Request) -> str | None:
    """request.state may be invisible across BaseHTTPMiddleware; fall back to contextvar."""
    state_val = getattr(request.state, "tenant_id", None)
    if state_val is not None:
        return str(state_val)
    return get_tenant_id()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = perf_counter()
        route = _route_label(request)
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (perf_counter() - started_at) * 1000
            domain_metrics.record_request(
                method=request.method,
                route=route,
                status_class="5xx",
                duration_ms=duration_ms,
            )
            # Handler usually already emitted application_error; do not duplicate traceback.
            if not was_application_error_logged(request):
                log_application_error(
                    exc,
                    request=request,
                    route=route,
                    status_code=500,
                    error_code="internal_error",
                    duration_ms=duration_ms,
                    include_traceback=True,
                )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        status_class = f"{response.status_code // 100}xx"
        # Route may resolve after matching; prefer template when available.
        route = _route_label(request)
        correlation_id = _correlation_id(request)
        tenant_id = _tenant_id(request)
        domain_metrics.record_request(
            method=request.method,
            route=route,
            status_class=status_class,
            duration_ms=duration_ms,
        )
        if not (response.status_code < 400 and route in _QUIET_SUCCESS_ROUTES):
            logger.info(
                "request_complete",
                method=request.method,
                route=route,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                correlation_id=correlation_id,
                tenant_id=tenant_id,
            )
        return response
