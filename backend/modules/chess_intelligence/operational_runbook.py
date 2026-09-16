"""§33 — operational runbook: map ops → existing CLI / catalog jobs / APIs.

No new shell scripts — reuse ``backend.scripts.*``, ``POST /chess/jobs``,
and analysis enqueue. Browse GETs stay sync-free (§25).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunbookOp:
    operation: str
    primary: str
    notes: str


RUNBOOK_OPS: tuple[RunbookOp, ...] = (
    RunbookOp(
        "bootstrap_historical_archive",
        "python -m backend.scripts.import_chess_pgn …  OR  POST /chess/jobs kind=pgn_import",
        "Selective caps; never beat-scheduled redownload",
    ),
    RunbookOp(
        "run_historical_famous_enrichment",
        "python -m backend.scripts.apply_famous_catalog …  OR  POST /chess/jobs kind=enrich_famous",
        "Metadata-only on existing ChessGame rows",
    ),
    RunbookOp(
        "run_recent_provider_sync",
        "POST /chess/jobs kind=provider_sync  OR  CatalogAdminSyncPanel",
        "Advances ChessProviderSyncState only on clean run",
    ),
    RunbookOp(
        "refresh_daily_puzzle",
        "POST /chess/puzzles/daily/refresh  OR  POST /chess/jobs kind=daily_puzzle_sync",
        "GET /puzzles/daily stays local-first",
    ),
    RunbookOp(
        "inspect_synchronization_state",
        "GET /chess/sync-states",
        "Shows HWM / last error / last job; ≠ ChessCatalogJob history",
    ),
    RunbookOp(
        "retry_failed_synchronization",
        "POST /chess/jobs kind=provider_sync (same params)",
        "HWM unchanged after failure — retry resumes with lookback overlap",
    ),
    RunbookOp(
        "reanalyze_changed_engine_profile",
        "POST /chess/games/{id}/analyze {depth|force|…}",
        "New analysis_fingerprint → new job; same profile reuses",
    ),
)


def runbook_operations() -> tuple[str, ...]:
    return tuple(op.operation for op in RUNBOOK_OPS)
