"""Correlation-ID propagation across middleware, logs, and error responses."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request

from backend.api.middleware.correlation_id import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    CorrelationIdMiddleware,
    _request_id,
)
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.core.error_handler import register_exception_handlers
from backend.core.logging import CorrelationIdFilter


def _mini_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping(request: Request) -> dict[str, Any]:
        return {
            "state": getattr(request.state, "correlation_id", None),
            "context": structlog.contextvars.get_contextvars().get("correlation_id"),
        }

    @app.get("/boom")
    async def boom() -> None:
        raise HTTPException(status_code=400, detail="nope")

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("explode")

    # Same order as api.main: logging then correlation (correlation outermost of the pair).
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    return app


def _get(
    path: str,
    *,
    headers: dict[str, str] | None = None,
    raise_app_exceptions: bool = True,
) -> httpx.Response:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=_mini_app(),
            raise_app_exceptions=raise_app_exceptions,
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, headers=headers)

    return asyncio.run(_request())


def test_request_id_accepts_safe_values_and_replaces_invalid_values() -> None:
    assert _request_id("request-123") == "request-123"
    generated = _request_id("bad request\nwith-newline")
    uuid.UUID(generated)


def test_stdlib_records_receive_correlation_context() -> None:
    structlog.contextvars.bind_contextvars(correlation_id="corr-123")
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
    assert CorrelationIdFilter().filter(record) is True
    assert record.correlation_id == "corr-123"
    structlog.contextvars.clear_contextvars()


def test_incoming_correlation_header_propagates_to_state_context_and_response(
    monkeypatch,
) -> None:
    events: list[dict[str, Any]] = []

    def _capture(event: str, **kwargs: Any) -> None:
        events.append({"event": event, **kwargs})

    monkeypatch.setattr(
        "backend.api.middleware.request_logging.logger.info",
        _capture,
    )
    response = _get("/ping", headers={CORRELATION_ID_HEADER: "corr-fixed-001"})
    assert response.status_code == 200
    assert response.headers.get(CORRELATION_ID_HEADER) == "corr-fixed-001"
    assert response.headers.get(REQUEST_ID_HEADER) == "corr-fixed-001"
    body = response.json()
    assert body["state"] == "corr-fixed-001"
    assert body["context"] == "corr-fixed-001"
    complete = [e for e in events if e.get("event") == "request_complete"]
    assert complete
    assert complete[0]["correlation_id"] == "corr-fixed-001"


def test_x_request_id_header_is_honored() -> None:
    response = _get("/ping", headers={REQUEST_ID_HEADER: "req-from-gateway"})
    assert response.headers.get(CORRELATION_ID_HEADER) == "req-from-gateway"
    assert response.json()["state"] == "req-from-gateway"


def test_generated_correlation_id_is_uuid_when_header_missing() -> None:
    response = _get("/ping")
    cid = response.headers.get(CORRELATION_ID_HEADER)
    assert cid
    uuid.UUID(cid)
    assert response.json()["state"] == cid


def test_http_error_payload_uses_same_correlation_id() -> None:
    response = _get("/boom", headers={CORRELATION_ID_HEADER: "corr-err-1"})
    assert response.status_code == 400
    assert response.headers.get(CORRELATION_ID_HEADER) == "corr-err-1"
    payload = response.json()["error"]
    assert payload["correlation_id"] == "corr-err-1"
    assert payload["request_id"] == "corr-err-1"


def test_unhandled_error_log_uses_correlation_id(monkeypatch) -> None:
    events: list[dict[str, Any]] = []

    def _capture(event: str, **kwargs: Any) -> None:
        events.append({"event": event, **kwargs})

    monkeypatch.setattr(
        "backend.core.app_errors.logger.exception",
        _capture,
    )
    response = _get(
        "/crash",
        headers={CORRELATION_ID_HEADER: "corr-crash-9"},
        raise_app_exceptions=False,
    )
    assert response.status_code == 500
    assert response.json()["error"]["correlation_id"] == "corr-crash-9"
    assert any(
        e.get("event") == "application_error" and e.get("correlation_id") == "corr-crash-9"
        for e in events
    )
