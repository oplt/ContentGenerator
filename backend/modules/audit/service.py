from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.models import AuditLog
from backend.modules.audit.repository import AuditRepository


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AuditRepository(db)

    async def record(
        self,
        *,
        tenant_id: UUID | None,
        actor_user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | None,
        message: str,
        payload: dict[str, object] | None = None,
        correlation_id: str | None = None,
        severity: str = "info",
        outcome: str | None = None,
        payload_schema: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            message=message,
            payload=payload or {},
            correlation_id=correlation_id,
            severity=severity,
            outcome=outcome,
            payload_schema=payload_schema,
        )
        return await self.repo.create(log)

    async def list_logs(self, *, tenant_id: UUID | None, limit: int = 50) -> list[AuditLog]:
        return await self.repo.list_logs(tenant_id=tenant_id, limit=limit)
