"""Sync automation_occurrences when a WorkflowRun reaches a terminal state."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.models import (
    AutomationOccurrence,
    AutomationOccurrenceStatus,
)
from backend.modules.workflows.run_models import WorkflowRun, WorkflowRunStatus

_OCCURRENCE_TERMINAL = {
    AutomationOccurrenceStatus.SUCCEEDED.value,
    AutomationOccurrenceStatus.FAILED.value,
    AutomationOccurrenceStatus.SKIPPED.value,
}


async def sync_occurrence_for_run(db: AsyncSession, run: WorkflowRun) -> None:
    """Map WorkflowRun terminal status onto the linked AutomationOccurrence."""
    if run.automation_id is None:
        return
    if run.status not in {
        WorkflowRunStatus.SUCCEEDED.value,
        WorkflowRunStatus.FAILED.value,
        WorkflowRunStatus.CANCELLED.value,
    }:
        return

    result = await db.execute(
        select(AutomationOccurrence).where(AutomationOccurrence.workflow_run_id == run.id)
    )
    occ = result.scalar_one_or_none()
    if occ is None:
        return
    if occ.status in _OCCURRENCE_TERMINAL:
        return

    if run.status == WorkflowRunStatus.SUCCEEDED.value:
        occ.status = AutomationOccurrenceStatus.SUCCEEDED.value
        occ.error_message = None
    elif run.status == WorkflowRunStatus.FAILED.value:
        occ.status = AutomationOccurrenceStatus.FAILED.value
        if run.error_message:
            occ.error_message = str(run.error_message)[:2000]
    else:
        # CANCELLED — treat as skipped slot (run abandoned, not a schedule failure).
        occ.status = AutomationOccurrenceStatus.SKIPPED.value
        occ.error_message = "workflow run cancelled"
