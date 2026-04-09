from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.operations.models import TaskExecution


class OperationsRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, task_execution: TaskExecution) -> TaskExecution:
        self.db.add(task_execution)
        await self.db.flush()
        return task_execution

    async def get(self, task_execution_id: UUID) -> TaskExecution | None:
        result = await self.db.execute(
            select(TaskExecution).where(TaskExecution.id == task_execution_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 50) -> list[TaskExecution]:
        result = await self.db.execute(
            select(TaskExecution).order_by(TaskExecution.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
