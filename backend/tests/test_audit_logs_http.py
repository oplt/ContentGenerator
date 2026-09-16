"""Audit logs page request — mixed JSON payloads must not 400."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI

from backend.api.deps.db import get_db
from backend.core.error_handler import register_exception_handlers
from backend.modules.audit import router as audit_router
from backend.modules.audit.schemas import AuditLogResponse


def test_audit_log_response_accepts_mixed_payload_values() -> None:
    row = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        actor_user_id=uuid4(),
        action="automations.created",
        entity_type="automation",
        entity_id=str(uuid4()),
        correlation_id="corr-1",
        message="created",
        payload={"enabled": True, "target_count": 2, "meta": {"k": "v"}},
    )
    parsed = AuditLogResponse.model_validate(row)
    assert parsed.payload["enabled"] is True
    assert parsed.payload["target_count"] == 2


def test_audit_logs_page_request_returns_200_with_mixed_payloads(monkeypatch) -> None:
    """Mirrors AuditPage: GET /api/v1/audit/logs?limit=50 with real-shaped payloads."""
    tenant_id = uuid4()

    class FakeService:
        def __init__(self, db):  # noqa: ANN001
            _ = db

        async def list_logs(self, *, tenant_id, limit):  # noqa: ANN001
            assert limit == 50
            return [
                SimpleNamespace(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor_user_id=None,
                    action="publishing.attempt",
                    entity_type="publishing_job",
                    entity_id="job-1",
                    correlation_id=None,
                    message="attempt recorded",
                    payload={"status": "succeeded", "retry_count": 0, "dry_run": False},
                )
            ]

    monkeypatch.setattr(audit_router, "AuditService", FakeService)

    app = FastAPI()
    app.include_router(audit_router.router, prefix="/api/v1/audit")

    async def _membership() -> SimpleNamespace:
        return SimpleNamespace(tenant_id=tenant_id)

    async def _db() -> object:
        return object()

    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/v1/audit/logs")
    for dep in route.dependant.dependencies:  # type: ignore[attr-defined]
        name = getattr(dep.call, "__name__", "")
        if name == "dependency":
            app.dependency_overrides[dep.call] = _membership
        elif name == "get_db":
            app.dependency_overrides[dep.call] = _db
    app.dependency_overrides[get_db] = _db
    register_exception_handlers(app)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/v1/audit/logs?limit=50")

    response = asyncio.run(_request())
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["payload"]["retry_count"] == 0
    assert body[0]["payload"]["dry_run"] is False
