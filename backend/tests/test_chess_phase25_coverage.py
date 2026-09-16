"""Phase 25 coverage map — each required chess test area has an owning module."""

from __future__ import annotations

from pathlib import Path

TESTS = Path(__file__).resolve().parent

# Area from prompt Phase 25 → owning automated test module(s).
PHASE25_COVERAGE: dict[str, tuple[str, ...]] = {
    "lichess_provider_parsing": (
        "test_lichess_masters_provider.py",
        "test_lichess_puzzles_provider.py",
    ),
    "provider_error_handling": ("test_chess_provider_http_reliability.py",),
    "pgn_retrieval": ("test_lichess_masters_provider.py",),
    "pgn_archive_streaming": ("test_pgn_archive_import.py",),
    "normalization": ("test_chess_intelligence_domain.py", "test_chess_intelligence_providers.py"),
    "fingerprinting": ("test_chess_intelligence_domain.py", "test_chess_dedupe.py"),
    "deduplication": ("test_chess_dedupe.py",),
    "famous_game_matching": ("test_famous_catalog.py",),
    "puzzle_parsing": (
        "test_lichess_puzzles_provider.py",
        "test_lichess_puzzle_dataset_import.py",
    ),
    "puzzle_solution_validation": ("test_chess_intelligence_providers.py",),
    "search_filters_pagination": ("test_chess_search_api.py",),
    "tenant_access": ("test_chess_tenant_isolation.py", "test_chess_video_model.py"),
    "game_video_handoff": ("test_chess_game_video_bridge.py",),
    "stockfish_score_normalization": ("test_chess_stockfish_analysis.py",),
    "critical_position_heuristics": ("test_chess_critical_moments.py",),
}


def test_phase25_owning_modules_exist() -> None:
    missing: list[str] = []
    for area, modules in PHASE25_COVERAGE.items():
        for name in modules:
            path = TESTS / name
            if not path.is_file():
                missing.append(f"{area}:{name}")
    assert not missing, f"Phase 25 coverage gaps: {missing}"
