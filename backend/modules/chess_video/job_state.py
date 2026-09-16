"""State-copy helpers for cached chess video renders."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.renderer import RENDERER_VERSION


def copy_cached_outputs(job: ChessVideoJob, cached: ChessVideoJob) -> None:
    job.status = ChessVideoJobStatus.COMPLETED.value
    job.stage = ChessVideoJobStatus.COMPLETED.value
    job.progress = 1.0
    job.video_storage_key = cached.video_storage_key
    job.video_public_url = cached.video_public_url
    job.thumbnail_storage_key = cached.thumbnail_storage_key
    job.thumbnail_public_url = cached.thumbnail_public_url
    job.duration_seconds = cached.duration_seconds
    job.width = cached.width
    job.height = cached.height
    job.file_size_bytes = cached.file_size_bytes
    job.renderer_version = cached.renderer_version or RENDERER_VERSION
    now = datetime.now(timezone.utc)
    job.completed_at = now
    job.started_at = job.started_at or now
    job.error_message = None
