from time import perf_counter

from backend.core.logging import get_logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = get_logger("backend.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration_ms, 2),
                correlation_id=getattr(request.state, "correlation_id", "n/a"),
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        logger.info(
            "request_complete",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            correlation_id=getattr(request.state, "correlation_id", "n/a"),
        )
        return response
