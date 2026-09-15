"""Worker concurrency caps vs DB pool / provider limits (Phase 14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from backend.core.config import settings
from backend.workers.task_policy import WORKER_QUEUE_GROUPS


@dataclass(frozen=True, slots=True)
class WorkloadCapacity:
    workload: str
    queues: tuple[str, ...]
    concurrency: int
    prefetch_multiplier: int
    db_pool_slots: int
    within_db_budget: bool


# Prefetch stays at 1 for long jobs so workers do not reserve excess messages.
_DEFAULT_PREFETCH: Final[int] = 1


def worker_db_pool_slots() -> int:
    """Max simultaneous DB checkouts a worker process should assume."""
    return settings.DB_POOL_WORKER_SIZE + settings.DB_POOL_WORKER_MAX_OVERFLOW


def concurrency_for_workload(workload: str) -> int:
    mapping = {
        "io": settings.CELERY_WORKER_IO_CONCURRENCY,
        "llm": settings.CELERY_WORKER_LLM_CONCURRENCY,
        "media": settings.CELERY_WORKER_MEDIA_CONCURRENCY,
        "publishing": settings.CELERY_WORKER_PUBLISHING_CONCURRENCY,
        "db": settings.CELERY_WORKER_DB_CONCURRENCY,
    }
    if workload not in mapping:
        raise KeyError(f"unknown workload: {workload}")
    return mapping[workload]


def prefetch_for_workload(workload: str) -> int:
    """Long / exclusive workloads keep prefetch=1; short I/O may use global setting."""
    if workload in {"media", "llm", "publishing", "db"}:
        return _DEFAULT_PREFETCH
    return min(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 2)


def capacity_snapshot() -> list[WorkloadCapacity]:
    slots = worker_db_pool_slots()
    rows: list[WorkloadCapacity] = []
    for workload, queues in WORKER_QUEUE_GROUPS.items():
        concurrency = concurrency_for_workload(workload)
        rows.append(
            WorkloadCapacity(
                workload=workload,
                queues=queues,
                concurrency=concurrency,
                prefetch_multiplier=prefetch_for_workload(workload),
                db_pool_slots=slots,
                # One in-flight task ≈ one checkout; concurrency must not exceed pool.
                within_db_budget=concurrency <= slots,
            )
        )
    return rows


def assert_concurrency_within_db_budget() -> None:
    """Raise if any specialized worker concurrency exceeds the worker DB pool."""
    offenders = [row for row in capacity_snapshot() if not row.within_db_budget]
    if not offenders:
        return
    detail = ", ".join(
        f"{row.workload}={row.concurrency}>{row.db_pool_slots}" for row in offenders
    )
    raise ValueError(
        "Celery worker concurrency exceeds DB pool budget "
        f"(DB_POOL_WORKER_SIZE+OVERFLOW={worker_db_pool_slots()}): {detail}"
    )


def celery_worker_argv(workload: str) -> list[str]:
    """Suggested CLI argv fragment for a specialized worker."""
    queues = ",".join(WORKER_QUEUE_GROUPS[workload])
    concurrency = concurrency_for_workload(workload)
    prefetch = prefetch_for_workload(workload)
    return [
        f"--queues={queues}",
        f"--concurrency={concurrency}",
        f"--prefetch-multiplier={prefetch}",
        f"--hostname=worker-{workload}@%h",
    ]
