import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.telemetry import bind_correlation_context

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = _request_id(
            request.headers.get(REQUEST_ID_HEADER)
            or request.headers.get(CORRELATION_ID_HEADER)
        )
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        bind_correlation_context(correlation_id)
        request.state.correlation_id = correlation_id
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = correlation_id
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
