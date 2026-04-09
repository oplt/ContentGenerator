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

    async def worker_status(self) -> list[dict[str, object]]:
        recent = await self.repo.list_recent(limit=100)
        grouped: dict[str, dict[str, object]] = {}
        for task in recent:
            bucket = grouped.setdefault(
                task.queue_name,
                {
                    "queue_name": task.queue_name,
                    "running": 0,
                    "failed": 0,
                    "completed": 0,
                    "recent_tasks": [],
                },
            )
            if task.status == "running":
                bucket["running"] = int(bucket["running"]) + 1
            elif task.status == "failed":
                bucket["failed"] = int(bucket["failed"]) + 1
            elif task.status == "completed":
                bucket["completed"] = int(bucket["completed"]) + 1
            recent_tasks = list(bucket["recent_tasks"])
            if len(recent_tasks) < 5:
                recent_tasks.append(
                    {
                        "task_name": task.task_name,
                        "status": task.status,
                        "progress": task.progress,
                        "started_at": task.started_at.isoformat() if task.started_at else None,
                        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                    }
                )
                bucket["recent_tasks"] = recent_tasks
        return list(grouped.values())
