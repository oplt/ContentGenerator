"""§30 hybrid testing coverage map — scenarios → existing owning modules.

Extends Phase 25 style; does **not** invent a second chess test architecture.
"""

from __future__ import annotations

from pathlib import Path

TESTS = Path(__file__).resolve().parent

# Prompt §30 scenario → owning automated test module(s).
SECTION30_COVERAGE: dict[str, tuple[str, ...]] = {
    "canonical_deduplication": (
        "test_chess_dedupe.py",
        "test_chess_fingerprint_dedupe.py",
        "test_chess_idempotency.py",
    ),
    "archive_idempotency": ("test_pgn_archive_import.py",),
    "source_deduplication": ("test_chess_dedupe.py", "test_chess_idempotency.py"),
    "incremental_synchronization": ("test_chess_provider_sync_state.py",),
    "failed_synchronization": (
        "test_chess_provider_sync_state.py",
        "test_chess_failure_semantics.py",
    ),
    "local_first_reads": (
        "test_chess_local_first.py",
        "test_chess_failure_semantics.py",
        "test_chess_ingestion_mode.py",
    ),
    "daily_puzzle": (
        "test_chess_daily_freshness.py",
        "test_chess_ingestion_mode.py",
        "test_chess_failure_semantics.py",
    ),
    "analysis_caching": ("test_chess_analysis_reuse.py", "test_chess_idempotency.py"),
    "changed_analysis_profile": ("test_chess_analysis_reuse.py",),
    "concurrent_analysis_requests": ("test_chess_analysis_reuse.py",),
    "video_integration": (
        "test_chess_game_video_bridge.py",
        "test_chess_video_boundary.py",
    ),
    "regression_manual_video_puzzle_famous_opportunity_import": (
        "test_chess_video_parser.py",
        "test_chess_search_api.py",
        "test_famous_catalog.py",
        "test_chess_content_opportunity.py",
        "test_pgn_archive_import.py",
        "test_chess_intelligence_providers.py",
    ),
}


def test_section30_owning_modules_exist() -> None:
    missing: list[str] = []
    for area, modules in SECTION30_COVERAGE.items():
        for name in modules:
            path = TESTS / name
            if not path.is_file():
                missing.append(f"{area}:{name}")
    assert not missing, f"§30 coverage gaps: {missing}"


def test_section30_covers_prompt_minimum_scenarios() -> None:
    required = {
        "canonical_deduplication",
        "archive_idempotency",
        "source_deduplication",
        "incremental_synchronization",
        "failed_synchronization",
        "local_first_reads",
        "daily_puzzle",
        "analysis_caching",
        "changed_analysis_profile",
        "concurrent_analysis_requests",
        "video_integration",
        "regression_manual_video_puzzle_famous_opportunity_import",
    }
    assert required <= set(SECTION30_COVERAGE)
