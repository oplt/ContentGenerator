"""Persistence helpers for automation scheduling."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.models import (
    Automation,
    AutomationOccurrence,
    AutomationOccurrenceStatus,
    AutomationTarget,
    AutomationTriggerType,
)


class AutomationSchedulerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim_due_automations(
        self, *, now: datetime | None = None, limit: int = 50
    ) -> list[Automation]:
        """Lock due schedule automations with ``FOR UPDATE SKIP LOCKED``.

        Holds row locks until the caller commits/rolls back so concurrent ticks
        cannot process the same automation twice. Occurrence UNIQUE remains the
        second idempotency boundary for a given scheduled slot.
        """
        as_of = now or datetime.now(timezone.utc)
        stmt = (
            select(Automation)
            .where(
                Automation.enabled.is_(True),
                Automation.trigger_type == AutomationTriggerType.SCHEDULE.value,
                Automation.deleted_at.is_(None),
                Automation.next_run_at.is_not(None),
                Automation.next_run_at <= as_of,
            )
            .order_by(Automation.next_run_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def claim_occurrence(
        self,
        *,
        tenant_id: UUID,
        automation_id: UUID,
        scheduled_for: datetime,
        scheduled_occurrence: str,
    ) -> AutomationOccurrence | None:
        """Insert occurrence row; None if UNIQUE conflict (already claimed)."""
        existing = await self.get_occurrence(automation_id, scheduled_occurrence)
        if existing is not None:
            return None
        row = AutomationOccurrence(
            tenant_id=tenant_id,
            automation_id=automation_id,
            scheduled_for=scheduled_for,
            scheduled_occurrence=scheduled_occurrence,
            status=AutomationOccurrenceStatus.CLAIMED.value,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(row)
                await self.db.flush()
        except IntegrityError:
            return None
        return row

    async def get_occurrence(
        self, automation_id: UUID, scheduled_occurrence: str
    ) -> AutomationOccurrence | None:
        result = await self.db.execute(
            select(AutomationOccurrence).where(
                AutomationOccurrence.automation_id == automation_id,
                AutomationOccurrence.scheduled_occurrence == scheduled_occurrence,
            )
        )
        return result.scalar_one_or_none()

    async def list_enabled_targets(
        self, tenant_id: UUID, automation_id: UUID
    ) -> list[AutomationTarget]:
        result = await self.db.execute(
            select(AutomationTarget).where(
                AutomationTarget.tenant_id == tenant_id,
                AutomationTarget.automation_id == automation_id,
                AutomationTarget.enabled.is_(True),
                AutomationTarget.deleted_at.is_(None),
            )
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
