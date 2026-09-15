"""Worker recovery / claim-lease policy gates (T8.2)."""

from __future__ import annotations

from backend.core.config import settings
from backend.workers.celery_app import celery_app
from backend.workers.task_policy import TASK_POLICIES, celery_task_kwargs


def test_celery_rejects_on_worker_lost() -> None:
    assert settings.CELERY_TASK_REJECT_ON_WORKER_LOST is True
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_publishing_claim_lease_bounds() -> None:
    assert settings.PUBLISHING_CLAIM_LEASE_SECONDS >= 60
    assert settings.PUBLISHING_MAX_ATTEMPTS >= 1
    assert settings.PUBLISHING_CLAIM_BATCH_SIZE >= 1


def test_publish_due_jobs_has_no_broad_autoretry() -> None:
    name = "backend.workers.tasks.publish_due_jobs_task"
    assert name in TASK_POLICIES
    kwargs = celery_task_kwargs(name)
    assert Exception not in kwargs.get("autoretry_for", ())
    assert TASK_POLICIES[name].max_retries == 0


def test_worker_prefetch_bounded() -> None:
    assert settings.CELERY_WORKER_PREFETCH_MULTIPLIER == 1
    assert celery_app.conf.worker_prefetch_multiplier == 1
