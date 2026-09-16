"""Synthetic LLM concurrency matrix (ops Phase 11).

Models a single Ollama process that serializes work: overlapping callers wait on
a process-wide lock. Higher asyncio concurrency does not improve wall throughput
when the GPU/CPU backend is already saturated — it only grows queue latency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter


@dataclass(frozen=True, slots=True)
class ConcurrencyBenchResult:
    concurrency: int
    jobs: int
    job_cost_s: float
    wall_s: float
    throughput_jobs_per_s: float
    mean_latency_s: float


async def _run_jobs(
    *,
    jobs: int,
    concurrency: int,
    job_cost_s: float,
    serialize_backend: bool,
) -> ConcurrencyBenchResult:
    """
    Run ``jobs`` fake LLM calls with at most ``concurrency`` in flight.

    When ``serialize_backend`` is True, a lock simulates one local Ollama process.
    """
    sem = asyncio.Semaphore(concurrency)
    backend_lock = asyncio.Lock() if serialize_backend else nullcontext_lock()
    latencies: list[float] = []

    async def one() -> None:
        async with sem:
            started = perf_counter()
            async with backend_lock:
                await asyncio.sleep(job_cost_s)
            latencies.append(perf_counter() - started)

    wall_started = perf_counter()
    await asyncio.gather(*(one() for _ in range(jobs)))
    wall_s = perf_counter() - wall_started
    return ConcurrencyBenchResult(
        concurrency=concurrency,
        jobs=jobs,
        job_cost_s=job_cost_s,
        wall_s=wall_s,
        throughput_jobs_per_s=jobs / wall_s if wall_s > 0 else 0.0,
        mean_latency_s=sum(latencies) / len(latencies) if latencies else 0.0,
    )


class nullcontext_lock:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


async def benchmark_llm_concurrency_matrix(
    *,
    levels: tuple[int, ...] = (1, 2, 4),
    jobs: int = 8,
    job_cost_s: float = 0.05,
    serialize_backend: bool = True,
) -> list[ConcurrencyBenchResult]:
    rows: list[ConcurrencyBenchResult] = []
    for level in levels:
        rows.append(
            await _run_jobs(
                jobs=jobs,
                concurrency=level,
                job_cost_s=job_cost_s,
                serialize_backend=serialize_backend,
            )
        )
    return rows


def recommend_llm_concurrency(rows: list[ConcurrencyBenchResult]) -> int:
    """
    Prefer the lowest concurrency that achieves ≥95% of peak throughput.

    On a serialized backend this is always 1.
    """
    if not rows:
        return 1
    peak = max(row.throughput_jobs_per_s for row in rows)
    for row in sorted(rows, key=lambda r: r.concurrency):
        if row.throughput_jobs_per_s >= peak * 0.95:
            return row.concurrency
    return rows[0].concurrency
