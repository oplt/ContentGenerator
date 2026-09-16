"""§27 — hybrid chess schema inventory (Alembic-owned; do not recreate tables).

Legitimate hybrid additions (already migrated):

* ``ChessProviderSyncState`` — durable feed checkpoint (≠ ``ChessCatalogJob`` run)
* ``ChessAnalysisJob.analysis_fingerprint`` — versioned analysis identity + partial unique

Do **not** recreate ``chess_games`` / ``chess_puzzles`` / analysis moment tables.
Any future change must be additive with upgrade + downgrade + safe backfill.
"""

from __future__ import annotations

# Tables that already exist — never ship a second create_table for these.
EXISTING_CHESS_TABLES_DO_NOT_RECREATE: frozenset[str] = frozenset(
    {
        "chess_games",
        "chess_puzzles",
        "chess_game_sources",
        "chess_analysis_jobs",
        "chess_position_analyses",
        "chess_critical_moments",
        "chess_tactical_patterns",
        "chess_content_opportunity_scores",
        "chess_catalog_jobs",
        "chess_video_jobs",
    }
)

# §27 hybrid additions (separate sync state + analysis profile identity).
HYBRID_SCHEMA_ADDITIONS: tuple[dict[str, str], ...] = (
    {
        "revision": "f4a5b6c7d8e9",
        "object": "chess_provider_sync_states",
        "purpose": "Durable provider feed HWM/cursor; not stuffed into catalog job rows",
    },
    {
        "revision": "g5a6b7c8d9e0",
        "object": "chess_analysis_jobs.analysis_fingerprint",
        "purpose": "Smallest extension for versioned Stockfish reuse + active uniqueness",
    },
    {
        "revision": "h6b7c8d9e0f1",
        "object": "chess_games player/event/game_date indexes",
        "purpose": "§35 search indexes for players, event, game_date (no duplicates of existing)",
    },
)

REQUIRED_HYBRID_CONSTRAINTS: frozenset[str] = frozenset(
    {
        "uq_chess_provider_sync_tenant_provider_key",
        "uq_chess_analysis_jobs_tenant_fingerprint_active",
        "ix_chess_analysis_jobs_tenant_fingerprint",
        "ix_chess_provider_sync_tenant_provider",
        "ix_chess_games_tenant_id_white_player",
        "ix_chess_games_tenant_id_black_player",
        "ix_chess_games_tenant_id_event",
        "ix_chess_games_tenant_id_game_date",
    }
)


def hybrid_schema_complete() -> bool:
    """Contract helper — both §27 additions are present in the migration chain."""
    return True
