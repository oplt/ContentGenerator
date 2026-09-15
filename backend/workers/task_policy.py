"""Celery task execution policy: timeouts, retries, ack, queue classes (T3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import httpx
from sqlalchemy.exc import DBAPIError, OperationalError


# Retry only infrastructure / provider blips — never permanent domain errors.
TRANSIENT_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    ConnectionError,
    TimeoutError,
    OSError,
    httpx.TransportError,
    httpx.TimeoutException,
    OperationalError,
    DBAPIError,
)


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    """Workload class + execution bounds for one Celery task."""

    # io | llm | media | publishing | db
    workload: str
    soft_time_limit: int
    time_limit: int
    max_retries: int
    # Late ack only when redelivery after crash is safe (idempotent side effects).
    acks_late: bool
    retry_backoff: bool = True
    retry_jitter: bool = True


# Soft < hard; hard kills the process after soft warning.
# Workload classes: io (HTTP/polling), llm (generation), media (CPU/ffmpeg/TTS/image),
# publishing (claim/provider), db (analytics aggregates / bulk persistence).
TASK_POLICIES: Final[dict[str, TaskPolicy]] = {
    "backend.workers.tasks.send_email_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=5,
        acks_late=False,  # SMTP send is not safely idempotent
    ),
    "backend.workers.tasks.poll_sources_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=2,
        acks_late=True,  # fan-out only
    ),
    "backend.workers.tasks.ingest_source_task": TaskPolicy(
        workload="io",
        soft_time_limit=240,
        time_limit=300,
        max_retries=3,
        acks_late=True,  # article dedupe / conflict-safe insert
    ),
    "backend.workers.tasks.generate_content_task": TaskPolicy(
        workload="llm",
        soft_time_limit=600,
        time_limit=720,
        max_retries=2,
        acks_late=False,  # LLM generation may not be idempotent
    ),
    "backend.workers.tasks.generate_image_asset_task": TaskPolicy(
        workload="media",
        soft_time_limit=180,
        time_limit=240,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.generate_tts_asset_task": TaskPolicy(
        workload="media",
        soft_time_limit=180,
        time_limit=240,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.generate_chess_video_task": TaskPolicy(
        workload="media",
        soft_time_limit=480,
        time_limit=600,
        max_retries=1,
        acks_late=True,
    ),
    "backend.workers.tasks.send_approval_task": TaskPolicy(
        workload="io",
        soft_time_limit=120,
        time_limit=180,
        max_retries=3,
        acks_late=False,  # may send duplicate Telegram/WhatsApp messages
    ),
    "backend.workers.tasks.publish_due_jobs_task": TaskPolicy(
        workload="publishing",
        soft_time_limit=180,
        time_limit=240,
        max_retries=0,
        acks_late=True,  # attempt keys + claim leases (T1.3)
        retry_backoff=False,
        retry_jitter=False,
    ),
    "backend.workers.tasks.process_webhook_inbox_task": TaskPolicy(
        workload="io",
        soft_time_limit=120,
        time_limit=180,
        max_retries=3,
        acks_late=True,  # inbox row processing is durable
    ),
    "backend.workers.tasks.expire_stale_approvals_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.expire_stale_briefs_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.rescore_clusters_task": TaskPolicy(
        workload="llm",
        soft_time_limit=300,
        time_limit=360,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.rescore_all_tenants_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=2,
        acks_late=True,
    ),
    "backend.workers.tasks.sync_analytics_task": TaskPolicy(
        workload="db",
        soft_time_limit=480,
        time_limit=600,
        max_retries=3,
        acks_late=True,  # snapshot upserts
    ),
    "backend.workers.tasks.fetch_trending_repos_task": TaskPolicy(
        workload="io",
        soft_time_limit=300,
        time_limit=360,
        max_retries=3,
        acks_late=True,
    ),
    "backend.workers.tasks.send_trending_repos_digest_task": TaskPolicy(
        workload="llm",
        soft_time_limit=600,
        time_limit=720,
        max_retries=2,
        acks_late=False,  # Telegram digest not idempotent
    ),
    "backend.workers.tasks.trending_repos_daily_fanout_task": TaskPolicy(
        workload="io",
        soft_time_limit=60,
        time_limit=90,
        max_retries=2,
        acks_late=True,
    ),
}


# Compose / ops: which queues each specialized worker should consume.
# Keep critical paths disjoint so LLM/media/publishing cannot starve ingestion.
WORKER_QUEUE_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "io": ("ingestion", "enrichment", "email", "approvals"),
    "llm": ("generation",),
    "media": ("video",),
    "publishing": ("publishing",),
    "db": ("analytics",),
}


def queue_for_workload(workload: str) -> str:
    """Primary queue name for a workload class (first entry in the group)."""
    return WORKER_QUEUE_GROUPS[workload][0]


def celery_task_kwargs(task_name: str) -> dict[str, Any]:
    """Build ``@celery_app.task(...)`` kwargs from the policy table."""
    policy = TASK_POLICIES[task_name]
    kwargs: dict[str, Any] = {
        "name": task_name,
        "soft_time_limit": policy.soft_time_limit,
        "time_limit": policy.time_limit,
        "acks_late": policy.acks_late,
        "reject_on_worker_lost": True,
        "max_retries": policy.max_retries,
    }
    if policy.max_retries > 0:
        kwargs["autoretry_for"] = TRANSIENT_EXCEPTIONS
        kwargs["retry_backoff"] = policy.retry_backoff
        kwargs["retry_jitter"] = policy.retry_jitter
    else:
        kwargs["autoretry_for"] = ()
    return kwargs


def queue_csv_for_workload(workload: str) -> str:
    queues = WORKER_QUEUE_GROUPS[workload]
    return ",".join(queues)
