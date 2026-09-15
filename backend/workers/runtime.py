from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from typing import TypeVar
from uuid import UUID

from backend.core.domain_metrics import domain_metrics
from backend.core.telemetry import bind_correlation_context
from backend.db.session import get_sessionmaker
from backend.modules.operations.models import TaskExecution
from backend.modules.operations.service import OperationsService

ResultT = TypeVar("ResultT")

_worker_loop: asyncio.AbstractEventLoop | None = None
_worker_loop_thread: threading.Thread | None = None
_worker_loop_ready = threading.Event()
_worker_loop_lock = threading.Lock()
_worker_queue: queue.Queue[tuple[Awaitable[object] | None, Future[object]]] = queue.Queue()


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop, _worker_loop_thread

    with _worker_loop_lock:
        if _worker_loop is not None and not _worker_loop.is_closed():
            return _worker_loop

        _worker_loop_ready.clear()
        loop = asyncio.new_event_loop()

        async def process_queue() -> None:
            while True:
                while True:
                    try:
                        coroutine, future = _worker_queue.get_nowait()
                    except queue.Empty:
                        break
                    if coroutine is None:
                        future.set_result(None)
                        return
                    asyncio.create_task(_complete(coroutine, future))
                await asyncio.sleep(0.001)

        async def _complete(coroutine: Awaitable[object], future: Future[object]) -> None:
            try:
                future.set_result(await coroutine)
            except BaseException as exc:
                future.set_exception(exc)

        def run_loop() -> None:
            asyncio.set_event_loop(loop)
            _worker_loop_ready.set()
            loop.run_until_complete(process_queue())
            loop.close()

        _worker_loop = loop
        _worker_loop_thread = threading.Thread(
            target=run_loop,
            name="celery-asyncio-loop",
            daemon=True,
        )
        _worker_loop_thread.start()

    _worker_loop_ready.wait()
    return loop


def _run_on_worker_loop(async_func: Callable[[], Awaitable[ResultT]]) -> ResultT:
    _get_worker_loop()
    coroutine = async_func()
    future: Future[object] = Future()
    _worker_queue.put((coroutine, future))
    return future.result()  # type: ignore[return-value]


def shutdown_worker_loop(cleanup: Callable[[], Awaitable[None]]) -> None:
    """Run async worker cleanup on the loop, then stop and join its thread."""
    global _worker_loop, _worker_loop_thread

    with _worker_loop_lock:
        loop = _worker_loop
        thread = _worker_loop_thread
        if loop is None or loop.is_closed():
            _worker_loop = None
            _worker_loop_thread = None
            return

    cleanup_future: Future[object] = Future()
    _worker_queue.put((cleanup(), cleanup_future))
    cleanup_future.result()
    stop_future: Future[object] = Future()
    _worker_queue.put((None, stop_future))
    stop_future.result()
    if thread is not None and thread is not threading.current_thread():
        thread.join()

    with _worker_loop_lock:
        _worker_loop = None
        _worker_loop_thread = None


def _queue_delay_ms(payload: dict[str, str] | None) -> float | None:
    if not payload:
        return None
    raw = payload.get("enqueued_at")
    if not raw:
        return None
    try:
        enqueued = float(raw)
    except ValueError:
        return None
    delay = (time.time() - enqueued) * 1000.0
    return delay if delay >= 0 else 0.0


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
    """
    Worker entrypoint owns the session transaction.

    start_task is committed first (visible running row). Operation work flushes
    only; success commits once. Failure rolls back operation writes, then
    records finish_task=failed in a fresh transaction.
    Split-phase workflows (publishing) may still commit inside ``operation``.
    """
    bind_correlation_context(correlation_id)
    started = time.perf_counter()
    queue_delay_ms = _queue_delay_ms(payload)
    outcome = "success"

    async def runner() -> ResultT:
        nonlocal outcome
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
            task_execution_id = task_execution.id

            try:
                result = await operation(db)
                # Reload in case operation committed/rolled back mid-flight.
                task = await db.get(TaskExecution, task_execution_id)
                if task is not None:
                    await operations.finish_task(
                        task,
                        status="completed",
                        result={"status": "ok"},
                    )
                await db.commit()
                return result
            except Exception as exc:
                outcome = "failure"
                await db.rollback()
                task = await db.get(TaskExecution, task_execution_id)
                if task is not None:
                    await operations.finish_task(
                        task,
                        status="failed",
                        error_message=str(exc),
                    )
                    await db.commit()
                raise

    try:
        return _run_on_worker_loop(runner)
    finally:
        domain_metrics.record_task(
            task=task_name,
            queue=queue_name,
            outcome=outcome,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            queue_delay_ms=queue_delay_ms,
        )


def run_detached_async_task(
        *,
        task_name: str,
        queue_name: str,
        tenant_id: UUID | None,
        entity_type: str | None,
        entity_id: str | None,
        celery_task_id: str | None,
        correlation_id: str | None,
        payload: dict[str, str] | None,
        operation: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
    """
    Like ``run_async_task`` but closes the ledger session before ``operation``.

    Use for workflows that open their own short-lived sessions around network I/O
    (ingestion split-phase, staged generation). The worker pool connection is not
    held during remote latency.
    """
    bind_correlation_context(correlation_id)
    started = time.perf_counter()
    queue_delay_ms = _queue_delay_ms(payload)
    outcome = "success"

    async def runner() -> ResultT:
        nonlocal outcome
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
            task_execution_id = task_execution.id

        try:
            result = await operation()
        except Exception as exc:
            outcome = "failure"
            async with SessionLocal() as db:
                operations = OperationsService(db)
                task = await db.get(TaskExecution, task_execution_id)
                if task is not None:
                    await operations.finish_task(
                        task,
                        status="failed",
                        error_message=str(exc),
                    )
                    await db.commit()
            raise

        async with SessionLocal() as db:
            operations = OperationsService(db)
            task = await db.get(TaskExecution, task_execution_id)
            if task is not None:
                await operations.finish_task(
                    task,
                    status="completed",
                    result={"status": "ok"},
                )
            await db.commit()
        return result

    try:
        return _run_on_worker_loop(runner)
    finally:
        domain_metrics.record_task(
            task=task_name,
            queue=queue_name,
            outcome=outcome,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            queue_delay_ms=queue_delay_ms,
        )


def run_async_task_simple(operation: Callable[..., Awaitable[ResultT]]) -> ResultT:
    """Entrypoint-owned session: commit success, rollback failure."""

    async def runner() -> ResultT:
        SessionLocal = get_sessionmaker()
        async with SessionLocal() as db:
            try:
                result = await operation(db)
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

    return _run_on_worker_loop(runner)
