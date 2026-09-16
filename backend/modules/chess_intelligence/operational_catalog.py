"""Operational chess catalog scope (§18) — not a universal game warehouse.

SignalForge stores material useful for content operations::

    historical/famous · master discovery · current events
    analysis · stories · puzzles · video · editorial workflows

Huge external archives stay outside Postgres::

    raw/compressed archive → object/file storage or external URI
           ↓
    streaming / selective import (filters + caps)
           ↓
    operational canonical ChessGame catalog

Do **not** download every chess game ever played into PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config import settings
from backend.modules.chess_intelligence.fingerprint import normalize_player_name
from backend.modules.chess_intelligence.normalizer import year_from_pgn_date

# Catalog / content workflows prioritize these use-cases (documentation + tests).
OPERATIONAL_CATALOG_PURPOSES: frozenset[str] = frozenset(
    {
        "historical_famous",
        "master_discovery",
        "current_events",
        "analysis",
        "story_generation",
        "puzzles",
        "video_generation",
        "editorial_workflows",
    }
)

# Content-opportunity score at/above this is a strong "notable" signal (§8) —
# not an automatic import gate; used by selection/workflows.
DEFAULT_CONTENT_OPPORTUNITY_THRESHOLD = 55


@dataclass(frozen=True, slots=True)
class SelectiveImportFilters:
    """Optional stream filters for archive/bootstrap import (§18).

    Empty/None fields mean "no restriction". Filters shrink what enters the
    operational catalog; they do not pull more from remote warehouses.
    """

    year_from: int | None = None
    year_to: int | None = None
    player: str | None = None  # white or black contains
    white: str | None = None
    black: str | None = None
    event: str | None = None
    min_rating: int | None = None  # either side >= when ratings present
    providers: frozenset[str] | None = None  # allowed source_provider labels


def filters_from_params(params: dict[str, Any] | None) -> SelectiveImportFilters:
    """Build filters from catalog-job / CLI params (missing keys = unrestricted)."""
    raw = params or {}
    providers_raw = raw.get("providers") or raw.get("source_filters")
    providers: frozenset[str] | None = None
    if isinstance(providers_raw, str) and providers_raw.strip():
        providers = frozenset(p.strip().lower() for p in providers_raw.split(",") if p.strip())
    elif isinstance(providers_raw, (list, tuple, set)):
        providers = frozenset(str(p).strip().lower() for p in providers_raw if str(p).strip())

    def _int(key: str) -> int | None:
        val = raw.get(key)
        if val is None or val == "":
            return None
        return int(val)

    def _str(key: str) -> str | None:
        val = raw.get(key)
        if val is None:
            return None
        text = str(val).strip()
        return text or None

    return SelectiveImportFilters(
        year_from=_int("year_from"),
        year_to=_int("year_to"),
        player=_str("player"),
        white=_str("white"),
        black=_str("black"),
        event=_str("event"),
        min_rating=_int("min_rating"),
        providers=providers,
    )


def clamp_pgn_import_max_games(max_games: int | None) -> int | None:
    """Apply configured ceiling so a single job cannot warehouse-dump unbounded."""
    cap = int(settings.CHESS_PGN_IMPORT_MAX_GAMES_CAP)
    if max_games is None:
        default = settings.CHESS_PGN_IMPORT_DEFAULT_MAX_GAMES
        if default is None:
            return None
        return min(max(int(default), 1), cap)
    return min(max(int(max_games), 1), cap)


def clamp_provider_sync_max_games(max_games: int | None) -> int:
    """Bounded recent-discovery pull (never an unbounded warehouse sync)."""
    cap = int(settings.CHESS_PROVIDER_SYNC_MAX_GAMES_CAP)
    raw = int(max_games) if max_games is not None else int(
        settings.CHESS_SCHEDULE_PROVIDER_SYNC_MAX_GAMES
    )
    return min(max(raw, 1), cap)


def _name_contains(haystack: str | None, needle: str) -> bool:
    if not haystack:
        return False
    return normalize_player_name(needle) in normalize_player_name(haystack)


def game_passes_selective_filters(
    *,
    white_player: str | None,
    black_player: str | None,
    event: str | None,
    game_date: str | None,
    year: int | None,
    white_rating: int | None,
    black_rating: int | None,
    source_provider: str | None,
    filters: SelectiveImportFilters,
) -> bool:
    """True when the candidate should enter the operational catalog."""
    resolved_year = year if year is not None else year_from_pgn_date(game_date)
    if filters.year_from is not None:
        if resolved_year is None or resolved_year < filters.year_from:
            return False
    if filters.year_to is not None:
        if resolved_year is None or resolved_year > filters.year_to:
            return False
    if filters.white and not _name_contains(white_player, filters.white):
        return False
    if filters.black and not _name_contains(black_player, filters.black):
        return False
    if filters.player:
        if not (
            _name_contains(white_player, filters.player)
            or _name_contains(black_player, filters.player)
        ):
            return False
    if filters.event:
        if not event or normalize_player_name(filters.event) not in normalize_player_name(
            event
        ):
            return False
    if filters.min_rating is not None:
        best = max(
            r for r in (white_rating, black_rating) if r is not None
        ) if (white_rating is not None or black_rating is not None) else None
        if best is None or best < filters.min_rating:
            return False
    if filters.providers is not None:
        provider = (source_provider or "").strip().lower()
        if provider not in filters.providers:
            return False
    return True
