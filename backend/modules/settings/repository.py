from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import Tenant


class SettingsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def list_tenants(self) -> list[Tenant]:
        result = await self.db.execute(select(Tenant))
        return list(result.scalars().all())
