import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("backend.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f correlation_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                getattr(request.state, "correlation_id", "n/a"),
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f correlation_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            getattr(request.state, "correlation_id", "n/a"),
        )
        return response
