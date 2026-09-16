"""Duplicate exception logging collapsed to one application_error."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Request

from backend.api.middleware.correlation_id import CORRELATION_ID_HEADER, CorrelationIdMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.core.app_errors import sanitize_error_text
from backend.core.error_handler import register_exception_handlers
from backend.core.request_context import set_tenant_id

TENANT = uuid4()


def _get(app: FastAPI, path: str, *, correlation_id: str) -> httpx.Response:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                path,
                headers={CORRELATION_ID_HEADER: correlation_id},
            )

    return asyncio.run(_request())


def test_sanitize_error_text_redacts_secrets_and_sql_noise() -> None:
    assert "[redacted]" in sanitize_error_text("password=supersecret token=abc")
    assert "params:" not in sanitize_error_text(
        'IntegrityError detail\n[SQL: INSERT ...]\nparams: {"token": "x"}'
    )


def test_unhandled_exception_logs_application_error_once(monkeypatch) -> None:
    events: list[dict[str, Any]] = []

    def _capture(event: str, **kwargs: Any) -> None:
        events.append({"event": event, **kwargs})

    monkeypatch.setattr("backend.core.app_errors.logger.exception", _capture)
    monkeypatch.setattr("backend.core.app_errors.logger.error", _capture)

    request_info: list[dict[str, Any]] = []

    def _capture_info(event: str, **kwargs: Any) -> None:
        request_info.append({"event": event, **kwargs})

    monkeypatch.setattr(
        "backend.api.middleware.request_logging.logger.info",
        _capture_info,
    )
    monkeypatch.setattr(
        "backend.api.middleware.request_logging.logger.exception",
        _capture_info,
    )

    app = FastAPI()

    @app.get("/boom")
    async def boom(request: Request) -> None:
        request.state.tenant_id = str(TENANT)
        set_tenant_id(TENANT)
        raise RuntimeError("db went boom password=leak")

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    response = _get(app, "/boom", correlation_id="corr-once-1")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["correlation_id"] == "corr-once-1"
    assert body["message"] == "An unexpected error occurred"
    assert "traceback" not in response.text.lower()
    assert "password" not in response.text.lower()

    app_errors = [e for e in events if e.get("event") == "application_error"]
    assert len(app_errors) == 1
    assert app_errors[0]["correlation_id"] == "corr-once-1"
    assert app_errors[0]["tenant_id"] == str(TENANT)
    assert app_errors[0]["error_type"] == "RuntimeError"
    assert app_errors[0]["error_code"] == "internal_error"
    assert "[redacted]" in app_errors[0]["error_message"]

    # Middleware may still emit request_complete for the 500 response — never a second traceback event.
    assert not any(e.get("event") == "request_failed" for e in request_info)


def test_failed_workflow_keeps_tenant_on_single_error_log(monkeypatch) -> None:
    events: list[dict[str, Any]] = []

    def _capture(event: str, **kwargs: Any) -> None:
        events.append({"event": event, **kwargs})

    monkeypatch.setattr("backend.core.app_errors.logger.exception", _capture)

    async def resolve_membership(request: Request) -> UUID:
        request.state.tenant_id = str(TENANT)
        set_tenant_id(TENANT)
        return TENANT

    app = FastAPI()

    @app.get("/api/v1/workflows/definitions")
    async def list_definitions(tenant_id: UUID = Depends(resolve_membership)) -> list[Any]:
        raise RuntimeError("deliberate repository failure")

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    response = _get(
        app,
        "/api/v1/workflows/definitions",
        correlation_id="corr-tenant-once",
    )
    assert response.status_code == 500
    assert response.json()["error"]["tenant_id"] == str(TENANT)

    app_errors = [e for e in events if e.get("event") == "application_error"]
    assert len(app_errors) == 1
    assert app_errors[0]["tenant_id"] == str(TENANT)
