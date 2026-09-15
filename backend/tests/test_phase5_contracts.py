"""Phase 5 — API contract regression coverage."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from backend.modules.audit import router as audit_router
from backend.modules.story_intelligence.schemas import StoryClusterResponse


def test_story_cluster_contract_uses_canonical_uuid() -> None:
    annotation = StoryClusterResponse.model_fields["id"].annotation
    assert "UUID" in str(annotation)


def test_unfiltered_audit_logs_use_safe_tenant_scoped_default(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeService:
        def __init__(self, db):
            pass

        async def list_logs(self, *, tenant_id, limit):
            calls.update(tenant_id=tenant_id, limit=limit)
            return []

    monkeypatch.setattr(audit_router, "AuditService", FakeService)

    class Membership:
        tenant_id = uuid4()

    result = asyncio.run(audit_router.list_audit_logs(limit=50, membership=Membership(), db=object()))

    assert result == []
    assert calls == {"tenant_id": Membership.tenant_id, "limit": 50}
