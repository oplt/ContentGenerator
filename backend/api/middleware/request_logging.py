from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger

logger = get_logger("backend.request")

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path[:64]
    return _UUID_RE.sub("{id}", request.url.path)[:64]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = perf_counter()
        route = _route_label(request)
        correlation_id = getattr(request.state, "correlation_id", "n/a")
        tenant_id = getattr(request.state, "tenant_id", None)
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            domain_metrics.record_request(
                method=request.method,
                route=route,
                status_class="5xx",
                duration_ms=duration_ms,
            )
            logger.exception(
                "request_failed",
                method=request.method,
                route=route,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                correlation_id=correlation_id,
                tenant_id=tenant_id,
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        status_class = f"{response.status_code // 100}xx"
        # Route may resolve after matching; prefer template when available.
        route = _route_label(request)
        tenant_id = getattr(request.state, "tenant_id", tenant_id)
        domain_metrics.record_request(
            method=request.method,
            route=route,
            status_class=status_class,
            duration_ms=duration_ms,
        )
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
