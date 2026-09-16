"""Tenant context survives exception paths after membership resolution."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Request

from backend.api.middleware.correlation_id import CORRELATION_ID_HEADER, CorrelationIdMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.core.error_handler import register_exception_handlers
from backend.core.request_context import get_tenant_id, set_tenant_id


TENANT = uuid4()


class BoomRepository:
    """Stand-in for a workflow repository that fails after tenant is known."""

    def list_definitions(self, tenant_id: UUID) -> list[Any]:
        assert tenant_id == TENANT
        raise RuntimeError("deliberate repository failure")


async def resolve_membership(request: Request) -> UUID:
    """Mirrors get_current_membership: bind tenant then hand UUID to the handler."""
    request.state.tenant_id = str(TENANT)
    set_tenant_id(TENANT)
    return TENANT


def _workflow_like_app() -> FastAPI:
    app = FastAPI()
    repo = BoomRepository()

    @app.get("/api/v1/workflows/definitions")
    async def list_definitions(tenant_id: UUID = Depends(resolve_membership)) -> list[Any]:
        assert get_tenant_id() == str(TENANT)
        return repo.list_definitions(tenant_id)

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    return app


def test_failed_workflow_request_log_keeps_tenant_id(monkeypatch) -> None:
    events: list[dict[str, Any]] = []

    def _capture(event: str, **kwargs: Any) -> None:
        events.append({"event": event, **kwargs})

    monkeypatch.setattr("backend.core.app_errors.logger.exception", _capture)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=_workflow_like_app(),
            raise_app_exceptions=False,
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(
                "/api/v1/workflows/definitions",
                headers={CORRELATION_ID_HEADER: "corr-tenant-keep-1"},
            )

    response = asyncio.run(_request())
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["correlation_id"] == "corr-tenant-keep-1"
    assert body["tenant_id"] == str(TENANT)

    app_errors = [e for e in events if e.get("event") == "application_error"]
    assert len(app_errors) == 1
    assert app_errors[0]["tenant_id"] == str(TENANT)
    assert app_errors[0]["correlation_id"] == "corr-tenant-keep-1"


def test_request_context_tenant_cleared_between_requests() -> None:
    from backend.core.request_context import clear_request_context, get_tenant_id, set_tenant_id

    set_tenant_id(TENANT)
    assert get_tenant_id() == str(TENANT)
    clear_request_context()
    assert get_tenant_id() is None
