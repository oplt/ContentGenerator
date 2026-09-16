"""§38 — hybrid chess implementation priority order (P0→P4).

Each priority lists work items + exit criteria + owning modules/tests already in
the tree. Use this as the delivery checklist — not a second roadmap system.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PriorityBand:
    id: str
    title: str
    work_items: tuple[str, ...]
    exit_criteria: str
    owners: tuple[str, ...]  # modules and/or test files under repo


PRIORITY_ORDER: tuple[PriorityBand, ...] = (
    PriorityBand(
        id="P0",
        title="Local-First Correctness",
        work_items=(
            "provider sync-state persistence",
            "incremental sync semantics",
            "local-first daily puzzle",
            "provider-outage fallback",
            "idempotency tests",
        ),
        exit_criteria="Normal chess catalog reads no longer require external providers.",
        owners=(
            "backend/modules/chess_intelligence/provider_sync_state.py",
            "backend/modules/chess_intelligence/local_first.py",
            "backend/modules/chess_intelligence/daily_freshness.py",
            "backend/modules/chess_intelligence/failure_semantics.py",
            "backend/modules/chess_intelligence/idempotency.py",
            "backend/tests/test_chess_local_first.py",
            "backend/tests/test_chess_provider_sync_state.py",
            "backend/tests/test_chess_failure_semantics.py",
            "backend/tests/test_chess_idempotency.py",
            "backend/tests/test_chess_ingestion_mode.py",
        ),
    ),
    PriorityBand(
        id="P1",
        title="Historical Hybrid Lifecycle",
        work_items=(
            "historical bootstrap semantics",
            "archive manifest/checksum only if required",
            "famous catalog idempotency",
            "source provenance",
            "historical refresh policy",
        ),
        exit_criteria=(
            "Historical/famous games can be bootstrapped once and used indefinitely "
            "without scheduled redownload."
        ),
        owners=(
            "backend/modules/chess_intelligence/ingestion_mode.py",
            "backend/modules/chess_intelligence/import_manifest.py",
            "backend/modules/chess_intelligence/historical_assets.py",
            "backend/modules/chess_intelligence/famous_policy.py",
            "backend/modules/chess_intelligence/provenance_service.py",
            "backend/tests/test_chess_historical_assets.py",
            "backend/tests/test_chess_import_manifest.py",
            "backend/tests/test_chess_famous_policy.py",
            "backend/tests/test_chess_provenance.py",
            "backend/tests/test_pgn_archive_import.py",
        ),
    ),
    PriorityBand(
        id="P2",
        title="Analysis Reuse",
        work_items=(
            "analysis fingerprint/profile",
            "completed/running analysis reuse",
            "concurrency protection",
            "force-reanalysis semantics",
            "engine-version awareness",
        ),
        exit_criteria="Identical analysis requests do not trigger duplicate Stockfish computation.",
        owners=(
            "backend/modules/chess_intelligence/analysis_fingerprint.py",
            "backend/modules/chess_intelligence/analysis_service.py",
            "backend/modules/chess_intelligence/analysis_history.py",
            "backend/tests/test_chess_analysis_reuse.py",
            "backend/tests/test_chess_analysis_history.py",
            "frontend/src/features/chess/AnalyzeGameAction.test.tsx",
        ),
    ),
    PriorityBand(
        id="P3",
        title="Recent Discovery → Content Opportunity",
        work_items=(
            "scheduled recent sync",
            "cheap eligibility filter",
            "optional Stockfish analysis",
            "critical moments",
            "content opportunity",
            "recent/notable presentation",
        ),
        exit_criteria=(
            "New games can become SignalForge content candidates without being "
            "mislabeled as historically famous."
        ),
        owners=(
            "backend/modules/chess_intelligence/catalog_schedule.py",
            "backend/modules/chess_intelligence/discovery_eligibility.py",
            "backend/modules/chess_intelligence/catalog_job_sync.py",
            "backend/modules/chess_intelligence/content_opportunity.py",
            "backend/modules/chess_intelligence/catalog_concepts.py",
            "backend/modules/chess_intelligence/engine/critical_moments.py",
            "backend/tests/test_chess_discovery_eligibility.py",
            "backend/tests/test_chess_catalog_concepts.py",
            "backend/tests/test_chess_catalog_schedule.py",
            "backend/tests/test_chess_content_opportunity.py",
        ),
    ),
    PriorityBand(
        id="P4",
        title="UX and Operations",
        work_items=(
            "freshness/source indicators",
            "admin synchronization controls",
            "runbooks",
            "metrics",
            "observability",
            "frontend tests",
            "documentation",
        ),
        exit_criteria="Operators and UI can sync, inspect freshness, and run hybrid ops without provider clients in the browser.",
        owners=(
            "backend/modules/chess_intelligence/admin_sync.py",
            "backend/modules/chess_intelligence/operational_runbook.py",
            "backend/modules/chess_intelligence/observability.py",
            "frontend/src/features/chess/sourceFreshness.ts",
            "frontend/src/features/chess/CatalogAdminSyncPanel.tsx",
            "frontend/src/features/chess/section31Coverage.test.ts",
            "docs/chess.md",
            "backend/tests/test_chess_admin_sync.py",
            "backend/tests/test_chess_operational_runbook.py",
            "backend/tests/test_chess_observability.py",
            "backend/tests/test_chess_documentation.py",
        ),
    ),
)


def priority_ids() -> tuple[str, ...]:
    return tuple(band.id for band in PRIORITY_ORDER)
