"""Puzzle catalog scope (§19) — separate from historical game storage.

Puzzles are high-volume and live on ``ChessPuzzle``, not ``ChessGame``.

::

    Lichess puzzle dump / daily API
           ↓
    stream + selective filters (rating, themes, popularity, opening, date, source, max)
           ↓
    ChessPuzzle rows only

Rules:

* Keep the existing ``ChessPuzzle`` abstraction — do not fork HybridPuzzle types.
* ``source_game_id`` / ``source_game_url`` are provenance links only; import must
  **never** auto-create ``ChessGame`` rows from puzzle source games.
* Do not require millions of puzzles in Postgres for v1; caps + filters keep the
  operational set small. Larger imports later reuse the same API/importer.
* Puzzle sync / daily refresh ≠ historical PGN bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config import settings

PUZZLE_INGESTION_FILTERS: frozenset[str] = frozenset(
    {
        "rating",
        "themes",
        "popularity",
        "opening",
        "date",
        "source",
        "maximum_records",
    }
)


@dataclass(frozen=True, slots=True)
class PuzzleImportFilters:
    """Configurable puzzle ingestion bounds (§19)."""

    min_rating: int | None = None
    max_rating: int | None = None
    min_popularity: int | None = None
    themes: tuple[str, ...] = ()
    openings: tuple[str, ...] = ()  # any-of match on opening_tags
    daily_date_from: str | None = None  # YYYY-MM-DD inclusive when daily_date present
    daily_date_to: str | None = None
    providers: frozenset[str] | None = None  # source/provider allow-list


def puzzle_filters_from_params(params: dict[str, Any] | None) -> PuzzleImportFilters:
    raw = params or {}

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

    themes_raw = raw.get("themes") or []
    if isinstance(themes_raw, str):
        themes = tuple(t.strip() for t in themes_raw.replace(",", " ").split() if t.strip())
    else:
        themes = tuple(str(t).strip() for t in themes_raw if str(t).strip())

    openings_raw = raw.get("openings") or raw.get("opening") or []
    if isinstance(openings_raw, str):
        openings = tuple(
            t.strip() for t in openings_raw.replace(",", " ").split() if t.strip()
        )
    else:
        openings = tuple(str(t).strip() for t in openings_raw if str(t).strip())

    providers_raw = raw.get("providers") or raw.get("source") or raw.get("sources")
    providers: frozenset[str] | None = None
    if isinstance(providers_raw, str) and providers_raw.strip():
        providers = frozenset(
            p.strip().lower() for p in providers_raw.replace(",", " ").split() if p.strip()
        )
    elif isinstance(providers_raw, (list, tuple, set)):
        providers = frozenset(str(p).strip().lower() for p in providers_raw if str(p).strip())

    return PuzzleImportFilters(
        min_rating=_int("min_rating"),
        max_rating=_int("max_rating"),
        min_popularity=_int("min_popularity"),
        themes=themes,
        openings=openings,
        daily_date_from=_str("daily_date_from") or _str("date_from"),
        daily_date_to=_str("daily_date_to") or _str("date_to"),
        providers=providers,
    )


def clamp_puzzle_import_limit(limit: int | None) -> int | None:
    """Cap puzzle bulk import so dumps cannot fill Postgres by accident."""
    cap = int(settings.CHESS_PUZZLE_IMPORT_MAX_RECORDS_CAP)
    if limit is None:
        default = settings.CHESS_PUZZLE_IMPORT_DEFAULT_LIMIT
        if default is None:
            return None
        return min(max(int(default), 1), cap)
    return min(max(int(limit), 1), cap)


def puzzle_passes_filters(
    *,
    rating: int | None,
    popularity: int | None,
    themes: list[str] | None,
    opening_tags: list[str] | None,
    daily_date: str | None,
    provider: str | None,
    filters: PuzzleImportFilters,
) -> bool:
    if filters.min_rating is not None and (rating is None or rating < filters.min_rating):
        return False
    if filters.max_rating is not None and (rating is None or rating > filters.max_rating):
        return False
    if filters.min_popularity is not None and (
        popularity is None or popularity < filters.min_popularity
    ):
        return False
    if filters.themes:
        have = {t.lower() for t in (themes or [])}
        if not {t.lower() for t in filters.themes}.issubset(have):
            return False
    if filters.openings:
        have_open = {t.lower() for t in (opening_tags or [])}
        want = {t.lower() for t in filters.openings}
        if have_open.isdisjoint(want):
            return False
    if filters.daily_date_from or filters.daily_date_to:
        if not daily_date:
            return False
        day = daily_date.strip()[:10]
        if filters.daily_date_from and day < filters.daily_date_from:
            return False
        if filters.daily_date_to and day > filters.daily_date_to:
            return False
    if filters.providers is not None:
        if (provider or "").strip().lower() not in filters.providers:
            return False
    return True


def puzzle_import_creates_games() -> bool:
    """Explicit contract: puzzle ingest never materializes ChessGame rows."""
    return False
