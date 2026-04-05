from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = structlog.get_logger(__name__)


def _error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    details: Mapping[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": getattr(request.state, "correlation_id", None),
        }
    }


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
        return JSONResponse(
            status_code=409,
            content=_error_payload(
                request,
                code="integrity_error",
                message="A conflicting record already exists",
                details={"db_error": str(exc.orig) if exc.orig else str(exc)},
            ),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=_error_payload(
                request,
                code="bad_request",
                message=str(exc),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            request_id=getattr(request.state, "correlation_id", None),
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request,
                code="internal_error",
                message="An unexpected error occurred",
            ),
        )
