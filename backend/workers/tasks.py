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
from backend.workers.task_defs.chess_analysis import analyze_chess_game_task
from backend.workers.task_defs.chess_catalog import run_chess_catalog_job_task
from backend.workers.task_defs.chess_video import generate_chess_video_task
from backend.workers.task_defs.ingestion import ingest_source_task, poll_sources_task
from backend.workers.task_defs.publishing import publish_due_jobs_task
from backend.workers.task_defs.stories import rescore_all_tenants_task, rescore_clusters_task
from backend.workers.task_defs.trending import (
    fetch_trending_repos_task,
    send_trending_repos_digest_task,
    trending_repos_daily_fanout_task,
)
from backend.workers.task_defs.workflows import (
    advance_workflow_run_task,
    execute_workflow_node_task,
    process_workflow_webhook_inbox_task,
    recover_stale_workflow_node_runs_task,
    resume_workflow_waiting_node_task,
    run_workflow_retention_task,
    tick_due_automations_task,
    wake_due_workflow_waits_task,
)

__all__ = [
    "send_email_task",
    "poll_sources_task",
    "ingest_source_task",
    "generate_content_task",
    "generate_image_asset_task",
    "generate_tts_asset_task",
    "generate_chess_video_task",
    "analyze_chess_game_task",
    "run_chess_catalog_job_task",
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
    "tick_due_automations_task",
    "advance_workflow_run_task",
    "execute_workflow_node_task",
    "process_workflow_webhook_inbox_task",
    "recover_stale_workflow_node_runs_task",
    "resume_workflow_waiting_node_task",
    "run_workflow_retention_task",
    "wake_due_workflow_waits_task",
]
