from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.models import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, log: AuditLog) -> AuditLog:
        self.db.add(log)
        await self.db.flush()
        return log

    async def list_logs(self, *, tenant_id: UUID | None, limit: int = 50) -> list[AuditLog]:
        query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        if tenant_id:
            query = query.where(AuditLog.tenant_id == tenant_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())
