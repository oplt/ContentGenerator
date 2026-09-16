"""DB-backed automation scheduler (Phase 7).

Celery Beat only ticks once/minute. Per-automation schedules live in Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import (
    Automation,
    AutomationOccurrenceStatus,
    AutomationTriggerType,
)
from backend.modules.workflows.schedule_next import compute_next_run_at, occurrence_key
from backend.modules.workflows.scheduler_repository import AutomationSchedulerRepository


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


@dataclass(slots=True)
class TickResult:
    automation_id: UUID
    scheduled_occurrence: str
    workflow_run_id: UUID | None
    status: str
    error: str | None = None


class AutomationScheduler:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AutomationSchedulerRepository(db)
        self.engine = WorkflowEngine(db)

    def compute_next(
        self, automation: Automation, *, after: datetime | None = None
    ) -> datetime:
        return compute_next_run_at(
            trigger_config=dict(automation.trigger_config or {}),
            timezone_name=automation.timezone or "UTC",
            after=after,
        )

    async def ensure_next_run_at(self, automation: Automation) -> Automation:
        """Set next_run_at when enabling a schedule automation."""
        if automation.trigger_type != AutomationTriggerType.SCHEDULE.value:
            return automation
        if automation.next_run_at is not None:
            return automation
        automation.next_run_at = self.compute_next(automation)
        await self.db.flush()
        return automation

    async def tick(
        self,
        *,
        now: datetime | None = None,
        limit: int = 50,
        enqueue_advance: bool = True,
    ) -> list[TickResult]:
        as_of = now or datetime.now(timezone.utc)
        due = await self.repo.claim_due_automations(now=as_of, limit=limit)
        results: list[TickResult] = []
        for automation in due:
            results.append(
                await self._fire_one(
                    automation, as_of=as_of, enqueue_advance=enqueue_advance
                )
            )
        return results

    async def _fire_one(
        self,
        automation: Automation,
        *,
        as_of: datetime,
        enqueue_advance: bool,
    ) -> TickResult:
        scheduled_for = automation.next_run_at or as_of
        key = occurrence_key(scheduled_for)
        occ = await self.repo.claim_occurrence(
            tenant_id=automation.tenant_id,
            automation_id=automation.id,
            scheduled_for=scheduled_for,
            scheduled_occurrence=key,
        )
        # Always advance next_run_at so a failed/duplicate slot cannot hot-loop.
        try:
            automation.next_run_at = self.compute_next(automation, after=scheduled_for)
        except Exception as exc:  # noqa: BLE001
            automation.enabled = False
            automation.next_run_at = None
            await self.db.flush()
            if occ is not None:
                occ.status = AutomationOccurrenceStatus.FAILED.value
                occ.error_message = f"next_run_at compute failed: {exc}"
            return TickResult(
                automation_id=automation.id,
                scheduled_occurrence=key,
                workflow_run_id=None,
                status="failed",
                error=str(exc),
            )

        if occ is None:
            await self.db.flush()
            return TickResult(
                automation_id=automation.id,
                scheduled_occurrence=key,
                workflow_run_id=None,
                status="skipped",
            )

        try:
            run = await self._start_scheduled_run(automation, scheduled_for=scheduled_for, key=key)
        except HTTPException as exc:
            occ.status = AutomationOccurrenceStatus.FAILED.value
            occ.error_message = str(exc.detail)
            automation.last_run_at = as_of
            await self.db.flush()
            return TickResult(
                automation_id=automation.id,
                scheduled_occurrence=key,
                workflow_run_id=None,
                status="failed",
                error=str(exc.detail),
            )
        except Exception as exc:  # noqa: BLE001
            occ.status = AutomationOccurrenceStatus.FAILED.value
            occ.error_message = str(exc)
            automation.last_run_at = as_of
            await self.db.flush()
            return TickResult(
                automation_id=automation.id,
                scheduled_occurrence=key,
                workflow_run_id=None,
                status="failed",
                error=str(exc),
            )

        occ.workflow_run_id = run.id
        occ.status = AutomationOccurrenceStatus.STARTED.value
        automation.last_run_at = as_of
        await self.db.flush()

        if enqueue_advance:
            self._enqueue_advance(automation.tenant_id, run.id)

        return TickResult(
            automation_id=automation.id,
            scheduled_occurrence=key,
            workflow_run_id=run.id,
            status="started",
        )

    async def _start_scheduled_run(
        self,
        automation: Automation,
        *,
        scheduled_for: datetime,
        key: str,
    ) -> Any:
        targets = await self.repo.list_enabled_targets(automation.tenant_id, automation.id)
        account_ids = [t.social_account_id for t in targets]
        ctx = CompileContext(
            social_account_ids=account_ids,
            require_publish_targets=bool(account_ids),
        )
        settings = _mapping(automation.settings)
        trigger_payload = {
            "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
            "scheduled_occurrence": key,
            "automation_id": str(automation.id),
            **_mapping(settings.get("trigger_payload")),
        }
        return await self.engine.start_run(
            tenant_id=automation.tenant_id,
            workflow_version_id=automation.workflow_version_id,
            trigger_payload=trigger_payload,
            initial_inputs=_mapping(settings.get("initial_inputs")),
            automation_id=automation.id,
            brand_id=automation.brand_id,
            correlation_id=f"sched:{automation.id}:{key}",
            compile_context=ctx,
            trigger_type=AutomationTriggerType.SCHEDULE.value,
            advance=False,
        )

    @staticmethod
    def _enqueue_advance(tenant_id: UUID, run_id: UUID) -> None:
        from backend.workers.tasks import advance_workflow_run_task

        advance_workflow_run_task.delay(tenant_id=str(tenant_id), run_id=str(run_id))
