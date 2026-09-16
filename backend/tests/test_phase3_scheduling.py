"""Phase 3 — Beat staggering and periodic task overlap contracts."""

from __future__ import annotations

import asyncio

from backend.workers.celery_app import celery_app
from backend.workers import task_lock


def test_maintenance_schedules_are_staggered_and_expiring() -> None:
    schedules = celery_app.conf.beat_schedule

    assert schedules["publish-due-jobs-every-minute"]["options"] == {"expires": 240}
    assert schedules["tick-due-automations-every-minute"]["options"] == {
        "countdown": 5,
        "expires": 240,
    }
    assert schedules["poll-sources-every-5-min"]["options"] == {"countdown": 10, "expires": 240}
    assert schedules["rescore-all-tenants-every-30-min"]["options"] == {
        "countdown": 20,
        "expires": 1_800,
    }
    assert schedules["expire-stale-approvals-every-30-min"]["options"] == {
        "countdown": 30,
        "expires": 1_800,
    }
    assert schedules["workflow-retention-hourly"]["options"] == {
        "countdown": 40,
        "expires": 3_500,
    }


def test_periodic_lock_allows_one_overlapping_execution(monkeypatch) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}

        async def set(self, key: str, value: str, *, nx: bool, px: int) -> bool:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

        async def eval(self, script: str, count: int, key: str, token: str) -> int:
            if self.values.get(key) == token:
                del self.values[key]
                return 1
            return 0

    fake = FakeRedis()
    monkeypatch.setattr(task_lock, "redis_client", fake)

    async def exercise() -> None:
        async with task_lock.periodic_task_lock("maintenance", ttl_seconds=60) as first:
            assert first is True
            async with task_lock.periodic_task_lock("maintenance", ttl_seconds=60) as second:
                assert second is False
        assert fake.values == {}

    asyncio.run(exercise())
