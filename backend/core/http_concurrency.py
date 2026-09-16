"""Bounded async mapping helpers for shared HTTP consumers."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


async def map_concurrent(
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    *,
    limit: int,
    return_exceptions: bool = True,
) -> list[R | BaseException]:
    """Run a worker with bounded concurrency while preserving input order."""
    if not items:
        return []
    if limit < 1:
        raise ValueError("limit must be >= 1")

    sem = asyncio.Semaphore(limit)
    results: list[R | BaseException | None] = [None] * len(items)

    async def _run(index: int, item: T) -> None:
        async with sem:
            try:
                results[index] = await worker(item)
            except Exception as exc:
                if return_exceptions:
                    results[index] = exc
                else:
                    raise

    async with asyncio.TaskGroup() as group:
        for index, item in enumerate(items):
            group.create_task(_run(index, item))

    return [item if item is not None else RuntimeError("missing result") for item in results]
