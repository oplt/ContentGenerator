"""Worker asyncio bridge regression tests."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.workers import runtime


def test_concurrent_async_operations_share_a_dedicated_loop() -> None:
    async def operation() -> str:
        await asyncio.sleep(0.01)
        return "ok"

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(runtime._run_on_worker_loop, operation) for _ in range(3)]
            assert [future.result() for future in futures] == ["ok", "ok", "ok"]
    finally:
        runtime.shutdown_worker_loop(lambda: asyncio.sleep(0))
