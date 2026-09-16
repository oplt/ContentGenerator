"""§14 — multi-profile analysis history selection (latest / preferred / matching)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from backend.modules.chess_intelligence.analysis_history import (
    select_analysis,
    select_latest,
    select_matching,
    select_preferred,
)
from backend.modules.chess_intelligence.models import ChessAnalysisJob, ChessAnalysisJobStatus


def _job(
    *,
    depth: int,
    status: str = ChessAnalysisJobStatus.COMPLETED.value,
    created_offset_hours: int = 0,
    fingerprint: str | None = None,
) -> ChessAnalysisJob:
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    job = ChessAnalysisJob(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        chess_game_id=uuid.uuid4(),
        status=status,
        depth=depth,
        hash_mb=64,
        threads=1,
        analysis_settings={"depth": depth},
        analysis_fingerprint=fingerprint or f"fp-d{depth}-{created_offset_hours}",
        ply_count=10,
    )
    job.created_at = now + timedelta(hours=created_offset_hours)
    job.updated_at = job.created_at
    return job


def test_select_preferred_picks_deeper_completed() -> None:
    shallow = _job(depth=12, created_offset_hours=2)
    deep = _job(depth=24, created_offset_hours=1)
    queued = _job(depth=30, status=ChessAnalysisJobStatus.QUEUED.value, created_offset_hours=3)
    assert select_preferred([shallow, deep, queued]) is deep


def test_select_latest_prefers_completed_over_newer_failed() -> None:
    done = _job(depth=12, created_offset_hours=1)
    failed = _job(
        depth=12,
        status=ChessAnalysisJobStatus.FAILED.value,
        created_offset_hours=5,
        fingerprint="fp-failed",
    )
    assert select_latest([done, failed]) is done


def test_select_matching_by_fingerprint_and_depth() -> None:
    a = _job(depth=12, fingerprint="aaa")
    b = _job(depth=24, fingerprint="bbb", created_offset_hours=1)
    assert select_matching([a, b], analysis_fingerprint="bbb") is b
    assert select_matching([a, b], depth=12) is a
    assert select_analysis([a, b], profile="preferred") is b


def test_different_fingerprints_coexist_in_list_semantics() -> None:
    """Document §14: depth profiles are independent identities."""
    jobs = [_job(depth=12), _job(depth=24, created_offset_hours=1)]
    assert len({j.analysis_fingerprint for j in jobs}) == 2
    assert select_preferred(jobs) is jobs[1]
