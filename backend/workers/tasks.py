"""Celery include target. Task bodies live in backend.workers.task_defs.*."""

from __future__ import annotations

from backend.workers.task_defs.analytics import sync_analytics_task
from backend.workers.task_defs.approvals import (
    expire_stale_approvals_task,
    expire_stale_briefs_task,
    process_webhook_inbox_task,
    send_approval_task,
)
from backend.workers.task_defs.email import send_email_task
from backend.workers.task_defs.generation import (
    generate_content_task,
    generate_image_asset_task,
    generate_tts_asset_task,
)
from backend.workers.task_defs.chess_video import generate_chess_video_task
from backend.workers.task_defs.ingestion import ingest_source_task, poll_sources_task
from backend.workers.task_defs.publishing import publish_due_jobs_task
from backend.workers.task_defs.stories import rescore_all_tenants_task, rescore_clusters_task
from backend.workers.task_defs.trending import (
    fetch_trending_repos_task,
    send_trending_repos_digest_task,
    trending_repos_daily_fanout_task,
)

__all__ = [
    "send_email_task",
    "poll_sources_task",
    "ingest_source_task",
    "generate_content_task",
    "generate_image_asset_task",
    "generate_tts_asset_task",
    "generate_chess_video_task",
    "send_approval_task",
    "publish_due_jobs_task",
    "process_webhook_inbox_task",
    "expire_stale_approvals_task",
    "expire_stale_briefs_task",
    "rescore_clusters_task",
    "sync_analytics_task",
    "fetch_trending_repos_task",
    "send_trending_repos_digest_task",
    "trending_repos_daily_fanout_task",
    "rescore_all_tenants_task",
]
