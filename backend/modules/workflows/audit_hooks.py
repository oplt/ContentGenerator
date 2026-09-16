"""Workflow audit event helpers (Phase 17)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService


async def record_workflow_audit(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    message: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    outcome: str = "success",
) -> None:
    await AuditService(db).record(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        message=message,
        payload=payload or {},
        correlation_id=correlation_id,
        outcome=outcome,
    )
