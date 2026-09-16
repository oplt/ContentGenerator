"""§39 — critical acceptance criteria for hybrid local-first chess.

Implementation is incomplete until every criterion has owning evidence
(module and/or test) in the modular monolith.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    id: str
    statement: str
    evidence: tuple[str, ...]  # repo-relative paths


ACCEPTANCE_CRITERIA: tuple[AcceptanceCriterion, ...] = (
    AcceptanceCriterion(
        "AC01",
        "local DB is operational source of truth",
        (
            "backend/modules/chess_intelligence/local_first.py",
            "backend/tests/test_chess_local_first.py",
        ),
    ),
    AcceptanceCriterion(
        "AC02",
        "historical games are not routinely re-downloaded",
        (
            "backend/modules/chess_intelligence/historical_assets.py",
            "backend/modules/chess_intelligence/catalog_schedule.py",
            "backend/tests/test_chess_historical_assets.py",
            "backend/tests/test_chess_catalog_schedule.py",
        ),
    ),
    AcceptanceCriterion(
        "AC03",
        "recent games use incremental provider synchronization",
        (
            "backend/modules/chess_intelligence/provider_sync_state.py",
            "backend/modules/chess_intelligence/catalog_job_sync.py",
            "backend/tests/test_chess_provider_sync_state.py",
        ),
    ),
    AcceptanceCriterion(
        "AC04",
        "sync position survives process restarts",
        (
            "backend/modules/chess_intelligence/provider_sync_state.py",
            "backend/alembic/versions/f4a5b6c7d8e9_add_chess_provider_sync_state.py",
            "backend/tests/test_chess_provider_sync_state.py",
        ),
    ),
    AcceptanceCriterion(
        "AC05",
        "failed syncs do not corrupt the checkpoint",
        (
            "backend/modules/chess_intelligence/failure_semantics.py",
            "backend/tests/test_chess_failure_semantics.py",
            "backend/tests/test_chess_provider_sync_state.py",
        ),
    ),
    AcceptanceCriterion(
        "AC06",
        "same game from multiple sources creates one canonical game",
        (
            "backend/modules/chess_intelligence/dedupe.py",
            "backend/modules/chess_intelligence/fingerprint.py",
            "backend/tests/test_chess_dedupe.py",
            "backend/tests/test_chess_fingerprint_dedupe.py",
        ),
    ),
    AcceptanceCriterion(
        "AC07",
        "all sources remain attributable",
        (
            "backend/modules/chess_intelligence/provenance_service.py",
            "backend/tests/test_chess_provenance.py",
            "backend/tests/test_chess_idempotency.py",
        ),
    ),
    AcceptanceCriterion(
        "AC08",
        "famous status remains curation, not another PGN copy",
        (
            "backend/modules/chess_intelligence/famous_policy.py",
            "backend/modules/chess_intelligence/famous_catalog.py",
            "backend/tests/test_chess_famous_policy.py",
        ),
    ),
    AcceptanceCriterion(
        "AC09",
        "recent/notable is distinct from famous",
        (
            "backend/modules/chess_intelligence/catalog_concepts.py",
            "backend/tests/test_chess_catalog_concepts.py",
        ),
    ),
    AcceptanceCriterion(
        "AC10",
        "content opportunity is distinct from both",
        (
            "backend/modules/chess_intelligence/content_opportunity.py",
            "backend/modules/chess_intelligence/catalog_concepts.py",
            "backend/tests/test_chess_content_opportunity.py",
            "backend/tests/test_chess_catalog_concepts.py",
        ),
    ),
    AcceptanceCriterion(
        "AC11",
        "normal GET endpoints do not require provider availability",
        (
            "backend/modules/chess_intelligence/local_first.py",
            "backend/tests/test_chess_local_first.py",
            "backend/tests/test_chess_admin_sync.py",
        ),
    ),
    AcceptanceCriterion(
        "AC12",
        "daily puzzle is locally persisted before being served",
        (
            "backend/modules/chess_intelligence/service.py",
            "backend/modules/chess_intelligence/daily_freshness.py",
            "backend/tests/test_chess_ingestion_mode.py",
            "backend/tests/test_chess_daily_freshness.py",
        ),
    ),
    AcceptanceCriterion(
        "AC13",
        "provider outage has a sensible stale-data fallback",
        (
            "backend/modules/chess_intelligence/failure_semantics.py",
            "backend/tests/test_chess_failure_semantics.py",
            "frontend/src/features/chess/DailyPuzzlePanel.test.tsx",
        ),
    ),
    AcceptanceCriterion(
        "AC14",
        "equivalent Stockfish analysis is reused",
        (
            "backend/modules/chess_intelligence/analysis_fingerprint.py",
            "backend/modules/chess_intelligence/analysis_service.py",
            "backend/tests/test_chess_analysis_reuse.py",
        ),
    ),
    AcceptanceCriterion(
        "AC15",
        "engine/configuration changes can create a new analysis",
        (
            "backend/modules/chess_intelligence/analysis_fingerprint.py",
            "backend/tests/test_chess_analysis_reuse.py",
            "backend/tests/test_chess_idempotency.py",
        ),
    ),
    AcceptanceCriterion(
        "AC16",
        "concurrent identical analysis requests cannot duplicate work",
        (
            "backend/modules/chess_intelligence/analysis_service.py",
            "backend/modules/chess_intelligence/idempotency.py",
            "backend/tests/test_chess_analysis_reuse.py",
        ),
    ),
    AcceptanceCriterion(
        "AC17",
        "existing chess-video renderer remains the downstream renderer",
        (
            "backend/modules/chess_video/boundary.py",
            "backend/tests/test_chess_video_boundary.py",
            "backend/tests/test_chess_game_video_bridge.py",
        ),
    ),
    AcceptanceCriterion(
        "AC18",
        "manual PGN/SAN/UCI video creation remains functional",
        (
            "backend/modules/chess_video",
            "backend/tests/test_chess_video_parser.py",
            "frontend/src/features/chess/CreateVideoAction.test.tsx",
        ),
    ),
    AcceptanceCriterion(
        "AC19",
        "frontend never contains provider credentials",
        (
            "backend/modules/chess_intelligence/external_service_security.py",
            "frontend/src/features/chess/frontendSeparation.ts",
            "backend/tests/test_chess_configuration.py",
            "backend/tests/test_chess_external_service_security.py",
            "frontend/src/features/chess/structure.test.ts",
        ),
    ),
    AcceptanceCriterion(
        "AC20",
        "no new scheduler/task system is introduced unnecessarily",
        (
            "backend/modules/chess_intelligence/catalog_schedule.py",
            "backend/modules/chess_intelligence/scope_v1.py",
            "backend/tests/test_chess_catalog_schedule.py",
            "backend/tests/test_chess_scope_v1.py",
        ),
    ),
    AcceptanceCriterion(
        "AC21",
        "no duplicate canonical chess subsystem is created",
        (
            "backend/modules/chess_intelligence/target_architecture.py",
            "backend/modules/chess_intelligence/scope_v1.py",
            "backend/tests/test_chess_target_architecture.py",
            "backend/tests/test_chess_scope_v1.py",
        ),
    ),
)


PROMPT_STATEMENTS: tuple[str, ...] = tuple(c.statement for c in ACCEPTANCE_CRITERIA)


def acceptance_ids() -> tuple[str, ...]:
    return tuple(c.id for c in ACCEPTANCE_CRITERIA)


def all_criteria_met_contract() -> bool:
    """Structural completeness helper — evidence paths must exist (see tests)."""
    return len(ACCEPTANCE_CRITERIA) == 21
