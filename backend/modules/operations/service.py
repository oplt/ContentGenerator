from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.operations.models import TaskExecution
from backend.modules.operations.repository import OperationsRepository


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OperationsRepository(db)

    async def start_task(
        self,
        *,
        task_name: str,
        queue_name: str,
        tenant_id: UUID | None,
        entity_type: str | None,
        entity_id: str | None,
        celery_task_id: str | None,
        correlation_id: str | None,
        payload: dict[str, str] | None = None,
        cancellable: bool = False,
    ) -> TaskExecution:
        task = TaskExecution(
            tenant_id=tenant_id,
            task_name=task_name,
            queue_name=queue_name,
            celery_task_id=celery_task_id,
            correlation_id=correlation_id,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
            status="running",
            progress=0,
            started_at=datetime.now(timezone.utc),
            cancellable=cancellable,
        )
        return await self.repo.create(task)

    async def update_progress(self, task: TaskExecution, progress: int, result: dict[str, str] | None = None) -> None:
        task.progress = progress
        if result is not None:
            task.result = result
        await self.db.flush()

    async def finish_task(
        self,
        task: TaskExecution,
        *,
        status: str,
        result: dict[str, str] | None = None,
        error_message: str | None = None,
    ) -> None:
        task.status = status
        task.result = result or {}
        task.error_message = error_message
        task.progress = 100 if status == "completed" else task.progress
        task.finished_at = datetime.now(timezone.utc)
        await self.db.flush()
