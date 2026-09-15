from __future__ import annotations

import time
from typing import Any

from backend.workers.celery_app import celery_app
from backend.workers.task_policy import celery_task_kwargs


def task(task_name: str) -> Any:
    return celery_app.task(**celery_task_kwargs(task_name))


def enqueue_payload(**extra: str) -> dict[str, str]:
    """Low-cardinality worker payload; includes enqueue timestamp for queue-delay metrics."""
    payload = {"enqueued_at": f"{time.time():.6f}"}
    payload.update(extra)
    return payload
