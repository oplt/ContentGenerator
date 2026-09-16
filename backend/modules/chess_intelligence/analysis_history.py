"""Multi-profile Stockfish analysis history selection (§14).

Raw results stay on per-job rows (``ChessPositionAnalysis`` FK → job).
Different engine/settings → different ``analysis_fingerprint`` → coexist.
"""

from __future__ import annotations

from typing import Literal

from backend.modules.chess_intelligence.models import ChessAnalysisJob, ChessAnalysisJobStatus

AnalysisProfile = Literal["latest", "preferred", "matching"]

COMPLETED = ChessAnalysisJobStatus.COMPLETED.value


def completed_jobs(jobs: list[ChessAnalysisJob]) -> list[ChessAnalysisJob]:
    return [j for j in jobs if j.status == COMPLETED]


def select_latest(jobs: list[ChessAnalysisJob]) -> ChessAnalysisJob | None:
    """Most recently created completed job; else most recent any status."""
    done = completed_jobs(jobs)
    pool = done or list(jobs)
    if not pool:
        return None
    return max(pool, key=lambda j: j.created_at)


def select_preferred(jobs: list[ChessAnalysisJob]) -> ChessAnalysisJob | None:
    """Best completed profile: higher depth, then newer. Fallback to latest."""
    done = completed_jobs(jobs)
    if not done:
        return select_latest(jobs)

    def _key(j: ChessAnalysisJob) -> tuple:
        depth = j.depth if j.depth is not None else -1
        return (depth, j.created_at)

    return max(done, key=_key)


def select_matching(
    jobs: list[ChessAnalysisJob],
    *,
    analysis_fingerprint: str | None = None,
    depth: int | None = None,
) -> ChessAnalysisJob | None:
    """Exact fingerprint, else completed job at depth, else preferred."""
    if analysis_fingerprint:
        hits = [j for j in jobs if j.analysis_fingerprint == analysis_fingerprint]
        return select_latest(hits) if hits else None
    if depth is not None:
        hits = [j for j in completed_jobs(jobs) if j.depth == depth]
        if hits:
            return select_latest(hits)
    return select_preferred(jobs)


def select_analysis(
    jobs: list[ChessAnalysisJob],
    *,
    profile: AnalysisProfile = "latest",
    analysis_fingerprint: str | None = None,
    depth: int | None = None,
) -> ChessAnalysisJob | None:
    if profile == "matching":
        return select_matching(
            jobs, analysis_fingerprint=analysis_fingerprint, depth=depth
        )
    if profile == "preferred":
        return select_preferred(jobs)
    return select_latest(jobs)
