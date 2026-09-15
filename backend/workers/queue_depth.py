"""Broker queue depth helpers (Redis list lengths for Celery queues)."""

from __future__ import annotations

from backend.core.cache import redis_client
from backend.core.config import settings


def known_celery_queues() -> tuple[str, ...]:
    return (
        settings.CELERY_QUEUE_INGESTION,
        settings.CELERY_QUEUE_ENRICHMENT,
        settings.CELERY_QUEUE_GENERATION,
        settings.CELERY_QUEUE_VIDEO,
        settings.CELERY_QUEUE_APPROVALS,
        settings.CELERY_QUEUE_PUBLISHING,
        settings.CELERY_QUEUE_ANALYTICS,
        settings.CELERY_QUEUE_EMAIL,
    )


async def broker_queue_depths() -> dict[str, int]:
    """
    Return pending message counts per Celery queue name.

    Celery's Redis transport stores ready messages in a LIST keyed by queue name.
    Missing keys report depth 0.
    """
    depths: dict[str, int] = {}
    for queue in known_celery_queues():
        try:
            depth = await redis_client.llen(queue)
            depths[queue] = int(depth or 0)
        except Exception:
            depths[queue] = -1
    return depths
