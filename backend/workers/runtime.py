from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from backend.db.session import get_sessionmaker
from backend.modules.operations.service import OperationsService

ResultT = TypeVar("ResultT")

_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop


def _run_on_worker_loop(async_func: Callable[[], Awaitable[ResultT]]) -> ResultT:
    loop = _get_worker_loop()
    return loop.run_until_complete(async_func())


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
        SessionLocal = get_sessionmaker()
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

    return _run_on_worker_loop(runner)


def run_async_task_simple(operation: Callable[..., Awaitable[ResultT]]) -> ResultT:
    async def runner() -> ResultT:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as db:
            result = await operation(db)
            await db.commit()
            return result

    return _run_on_worker_loop(runner)