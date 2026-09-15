"""Phase 14 — worker concurrency vs DB pool and queue depth contracts."""

from __future__ import annotations

import pytest

from backend.workers.queue_depth import known_celery_queues
from backend.workers.task_policy import TASK_POLICIES, WORKER_QUEUE_GROUPS
from backend.workers.worker_capacity import (
    assert_concurrency_within_db_budget,
    capacity_snapshot,
    celery_worker_argv,
    concurrency_for_workload,
    prefetch_for_workload,
    worker_db_pool_slots,
)


def test_default_concurrency_fits_worker_db_pool() -> None:
    assert_concurrency_within_db_budget()
    slots = worker_db_pool_slots()
    for row in capacity_snapshot():
        assert row.concurrency <= slots
        assert row.within_db_budget is True


def test_oversized_concurrency_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.workers.worker_capacity as cap

    monkeypatch.setattr(
        cap,
        "settings",
        type(
            "S",
            (),
            {
                "DB_POOL_WORKER_SIZE": 1,
                "DB_POOL_WORKER_MAX_OVERFLOW": 0,
                "CELERY_WORKER_IO_CONCURRENCY": 4,
                "CELERY_WORKER_LLM_CONCURRENCY": 1,
                "CELERY_WORKER_MEDIA_CONCURRENCY": 1,
                "CELERY_WORKER_PUBLISHING_CONCURRENCY": 1,
                "CELERY_WORKER_DB_CONCURRENCY": 1,
                "CELERY_WORKER_PREFETCH_MULTIPLIER": 1,
            },
        )(),
    )
    with pytest.raises(ValueError, match="exceeds DB pool budget"):
        assert_concurrency_within_db_budget()


def test_long_workloads_use_prefetch_one() -> None:
    for workload in ("llm", "media", "publishing", "db"):
        assert prefetch_for_workload(workload) == 1


def test_celery_worker_argv_matches_queue_groups() -> None:
    argv = celery_worker_argv("media")
    assert "--queues=video" in argv
    assert f"--concurrency={concurrency_for_workload('media')}" in argv
    assert "--prefetch-multiplier=1" in argv


def test_every_task_workload_has_queue_group() -> None:
    for name, policy in TASK_POLICIES.items():
        assert policy.workload in WORKER_QUEUE_GROUPS, name


def test_known_celery_queues_cover_all_groups() -> None:
    known = set(known_celery_queues())
    for queues in WORKER_QUEUE_GROUPS.values():
        assert set(queues).issubset(known)
