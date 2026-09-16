from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.app_errors import log_application_error
from backend.core.request_context import get_correlation_id, get_tenant_id


def _error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    details: Mapping[str, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    correlation_id = getattr(request.state, "correlation_id", None) or get_correlation_id()
    tenant_id = getattr(request.state, "tenant_id", None) or get_tenant_id()
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            # One ID for the request lifecycle (request_id kept as alias).
            "correlation_id": correlation_id,
            "request_id": correlation_id,
            "tenant_id": tenant_id,
        }
    }


def _route_label(request: Request) -> str | None:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        details = exc.detail if isinstance(exc.detail, (dict, list)) else None
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                request,
                code=f"http_{exc.status_code}",
                message=message,
                details=details,
            ),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                request,
                code="validation_error",
                message="Request validation failed",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        # Log once without SQL bind parameters in the client payload.
        log_application_error(
            exc,
            request=request,
            route=_route_label(request),
            status_code=409,
            error_code="integrity_error",
            include_traceback=False,
        )
        return JSONResponse(
            status_code=409,
            content=_error_payload(
                request,
                code="integrity_error",
                message="A conflicting record already exists",
            ),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        # Pydantic ValidationError subclasses ValueError — treat as internal, not 400.
        if isinstance(exc, ValidationError):
            log_application_error(
                exc,
                request=request,
                route=_route_label(request),
                status_code=500,
                error_code="internal_error",
                include_traceback=True,
            )
            return JSONResponse(
                status_code=500,
                content=_error_payload(
                    request,
                    code="internal_error",
                    message="An unexpected error occurred",
                ),
            )
        return JSONResponse(
            status_code=400,
            content=_error_payload(
                request,
                code="bad_request",
                message=str(exc),
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        log_application_error(
            exc,
            request=request,
            route=_route_label(request),
            status_code=500,
            error_code="database_error",
            include_traceback=True,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request,
                code="internal_error",
                message="An unexpected error occurred",
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log_application_error(
            exc,
            request=request,
            route=_route_label(request),
            status_code=500,
            error_code="internal_error",
            include_traceback=True,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request,
                code="internal_error",
                message="An unexpected error occurred",
            ),
        )
