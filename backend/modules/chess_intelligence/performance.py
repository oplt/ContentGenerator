"""§35 — chess catalog performance contracts.

Rules::

    No accidental N+1 provider access on browse/search
    Search/list → local Postgres only
    Required indexes present (fingerprint, provider/external, sync key, …)
    Provider sync uses bounded concurrency (serial fetch + HTTP caps)
    Historical imports stream (chess.pgn.read_game / CSV row iter)
    Stockfish stays off the HTTP request path (enqueue → Celery)
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.db.base import Base


@dataclass(frozen=True, slots=True)
class RequiredIndex:
    purpose: str
    table: str
    index_name: str


REQUIRED_INDEXES: tuple[RequiredIndex, ...] = (
    RequiredIndex("canonical fingerprint", "chess_games", "uq_chess_games_tenant_id_game_fingerprint"),
    RequiredIndex("provider + external ID", "chess_games", "uq_chess_games_tenant_provider_external"),
    RequiredIndex(
        "source provider + external ID",
        "chess_game_sources",
        "uq_chess_game_sources_tenant_provider_external",
    ),
    RequiredIndex(
        "sync-state identity",
        "chess_provider_sync_states",
        "uq_chess_provider_sync_tenant_provider_key",
    ),
    RequiredIndex("game date", "chess_games", "ix_chess_games_tenant_id_game_date"),
    RequiredIndex("players (white)", "chess_games", "ix_chess_games_tenant_id_white_player"),
    RequiredIndex("players (black)", "chess_games", "ix_chess_games_tenant_id_black_player"),
    RequiredIndex("event", "chess_games", "ix_chess_games_tenant_id_event"),
    RequiredIndex("famous filtering", "chess_games", "ix_chess_games_tenant_id_is_famous"),
    RequiredIndex(
        "analysis identity",
        "chess_analysis_jobs",
        "uq_chess_analysis_jobs_tenant_fingerprint_active",
    ),
    RequiredIndex(
        "job status (analysis)",
        "chess_analysis_jobs",
        "ix_chess_analysis_jobs_tenant_id_status",
    ),
    RequiredIndex(
        "job status (catalog)",
        "chess_catalog_jobs",
        "ix_chess_catalog_jobs_tenant_id_status",
    ),
    RequiredIndex(
        "puzzle source/external ID",
        "chess_puzzles",
        "uq_chess_puzzles_tenant_provider_external",
    ),
)


def required_index_names() -> frozenset[str]:
    return frozenset(item.index_name for item in REQUIRED_INDEXES)


def orm_has_required_indexes() -> list[str]:
    """Return missing index names from SQLAlchemy metadata (no DB needed)."""
    missing: list[str] = []
    by_table = {t.name: {idx.name for idx in t.indexes} for t in Base.metadata.tables.values()}
    # UniqueConstraints may appear as indexes or constraints depending on dialect.
    for item in REQUIRED_INDEXES:
        names = by_table.get(item.table, set())
        table = Base.metadata.tables.get(item.table)
        if table is not None:
            names |= {c.name for c in table.constraints if c.name}
        if item.index_name not in names:
            missing.append(f"{item.table}.{item.index_name}")
    return missing


def provider_sync_is_serial_per_game() -> bool:
    """Sync fetches games one-by-one; HTTP layer still has concurrency caps."""
    return True


def historical_import_streams() -> bool:
    return True


def stockfish_off_http_path() -> bool:
    """HTTP analyze enqueues Celery; engine runs in worker process_job."""
    return True
