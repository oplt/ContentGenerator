from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from backend.db.session import SessionLocal
from backend.modules.operations.service import OperationsService


ResultT = TypeVar("ResultT")


def run_async_task(
    *,
    task_name: str,
    queue_name: str,
    tenant_id: UUID | None,
    entity_type: str | None,
    entity_id: str | None,
    celery_task_id: str | None,
    correlation_id: str | None,
    payload: dict[str, str] | None,
    operation: Callable[..., Awaitable[ResultT]],
) -> ResultT:
    async def runner() -> ResultT:
        async with SessionLocal() as db:
            operations = OperationsService(db)
            task_execution = await operations.start_task(
                task_name=task_name,
                queue_name=queue_name,
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                celery_task_id=celery_task_id,
                correlation_id=correlation_id,
                payload=payload,
            )
            await db.commit()
            try:
                result = await operation(db)
                await operations.finish_task(
                    task_execution,
                    status="completed",
                    result={"status": "ok"},
                )
                await db.commit()
                return result
            except Exception as exc:
                await operations.finish_task(
                    task_execution,
                    status="failed",
                    error_message=str(exc),
                )
                await db.commit()
                raise

    return asyncio.run(runner())


def run_async_task_simple(operation: Callable[..., Awaitable[ResultT]]) -> ResultT:
    """
    Lightweight wrapper for tasks that don't need TaskExecution tracking.
    Used by fan-out tasks like rescore_all_tenants_task.
    """
    async def runner() -> ResultT:
        async with SessionLocal() as db:
            result = await operation(db)
            await db.commit()
            return result

    return asyncio.run(runner())
