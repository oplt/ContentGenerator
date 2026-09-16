"""Automation persistence (Phase 13 API)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.models import Automation, AutomationTarget


class AutomationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_automations(self, tenant_id: UUID) -> list[Automation]:
        result = await self.db.execute(
            select(Automation)
            .where(Automation.tenant_id == tenant_id, Automation.deleted_at.is_(None))
            .order_by(Automation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_automation(self, tenant_id: UUID, automation_id: UUID) -> Automation | None:
        result = await self.db.execute(
            select(Automation).where(
                Automation.tenant_id == tenant_id,
                Automation.id == automation_id,
                Automation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def add_automation(self, automation: Automation) -> Automation:
        self.db.add(automation)
        await self.db.flush()
        return automation

    async def list_targets(self, tenant_id: UUID, automation_id: UUID) -> list[AutomationTarget]:
        result = await self.db.execute(
            select(AutomationTarget).where(
                AutomationTarget.tenant_id == tenant_id,
                AutomationTarget.automation_id == automation_id,
                AutomationTarget.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def replace_targets(
        self,
        *,
        tenant_id: UUID,
        automation_id: UUID,
        social_account_ids: list[UUID],
    ) -> list[AutomationTarget]:
        now = datetime.now(timezone.utc)
        existing = await self.list_targets(tenant_id, automation_id)
        for row in existing:
            if row.deleted_at is None:
                row.deleted_at = now
        created: list[AutomationTarget] = []
        for account_id in social_account_ids:
            target = AutomationTarget(
                tenant_id=tenant_id,
                automation_id=automation_id,
                social_account_id=account_id,
                enabled=True,
                overrides_json={},
            )
            self.db.add(target)
            created.append(target)
        await self.db.flush()
        return created
