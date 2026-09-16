"""Local-first policy for user-facing chess catalog reads (§9).

Normal GET/read path::

    frontend → SignalForge API → local PostgreSQL

Provider HTTP belongs on::

    catalog jobs / Celery sync
    manual import
    administrative refresh

not on browse/search/detail/daily-puzzle GETs.
"""

from __future__ import annotations

# Router paths (relative to ``/api/v1/chess``) that must not call live providers.
LOCAL_FIRST_GET_PATHS: frozenset[str] = frozenset(
    {
        "/games",
        "/games/famous",
        "/games/{game_id}",
        "/games/{game_id}/moves",
        "/games/{game_id}/analysis",
        "/games/{game_id}/analyses",
        "/games/{game_id}/content-score",
        "/analysis/{job_id}",
        "/puzzles",
        "/puzzles/daily",
        "/puzzles/{puzzle_id}",
    }
)

# Service methods that implement those reads — must not instantiate providers.
LOCAL_FIRST_SERVICE_METHODS: frozenset[str] = frozenset(
    {
        "list_games",
        "get_game",
        "get_game_moves",
        "list_puzzles",
        "get_puzzle",
        "get_daily_puzzle",
    }
)

# Explicit sync/admin entrypoints (provider OK).
PROVIDER_ALLOWED_ENTRYPOINTS: frozenset[str] = frozenset(
    {
        "sync_daily_puzzle",
        "provider_sync",
        "import_game",
        "pgn_import",
        "puzzle_import",
        "daily_puzzle_sync",
        "enrich_famous",
        "extract_critical_moments",
    }
)
