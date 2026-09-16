"""§25 — administrative catalog sync vs browse reads.

Browse/search GETs must never enqueue provider synchronization.
Privileged ops go through ``ChessCatalogJob`` / existing analysis enqueue.
"""

from __future__ import annotations

# User-facing admin actions → catalog job kinds (or dedicated analysis API).
ADMIN_SYNC_ACTIONS: dict[str, str] = {
    "run_recent_game_sync": "provider_sync",
    "refresh_daily_puzzle": "daily_puzzle_sync",
    "import_archive": "pgn_import",
    "enrich_famous_catalog": "enrich_famous",
    # Reanalyze uses ChessAnalysisService (fingerprint-aware), not catalog jobs.
    "reanalyze_stockfish": "analyze_chess_game",
}

# Read paths that must remain sync-free (relative to /api/v1/chess).
BROWSE_GET_MUST_NOT_SYNC: frozenset[str] = frozenset(
    {
        "/games",
        "/games/famous",
        "/games/{game_id}",
        "/games/{game_id}/moves",
        "/puzzles",
        "/puzzles/daily",
        "/puzzles/{puzzle_id}",
    }
)


def browse_gets_must_not_start_sync() -> bool:
    """Contract helper for tests/docs."""
    return True
