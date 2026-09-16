"""Historical chess games as durable local catalog assets.

Lifecycle (existing ``PgnArchiveImporter`` — do not fork a second importer)::

    Historical PGN source
           ↓
    acquire / stream parse
           ↓
    normalize → fingerprint → dedupe
           ↓
    local ChessGame + ChessGameSource
           ↓
    optional famous curation (metadata only)

Policy:

* Bootstrap / version-triggered archive import only — never a daily full redownload.
* Same archive identity re-run → ``inserted=0``, ``linked_source=0``, ``skipped_duplicate=N``.
* Existing games keep ``normalized_pgn`` / fingerprints; later sightings may only fill sparse blanks.
* Famous enrichment marks existing rows; it does not fetch PGN again.
* Fame is editorial classification on ``ChessGame`` — no parallel FamousGame table.
"""

from __future__ import annotations

from typing import Any

# Core identity fields must never be overwritten on fingerprint hit.
IMMUTABLE_GAME_FIELDS: frozenset[str] = frozenset(
    {
        "normalized_pgn",
        "game_fingerprint",
        "content_hash",
        "starting_fen",
        "move_count",
        "final_fen",
    }
)

# Celery beat must not auto-run historical PGN bootstrap / famous PGN redownload.
FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS: frozenset[str] = frozenset(
    {
        "pgn_import",
        "historical_bootstrap",
        "import_chess_pgn",
        "pgn_archive",
        "redownload_famous",
        "famous_pgn",
        "famous_bootstrap",
    }
)


def beat_entry_text(name: str, entry: dict[str, Any]) -> str:
    """Flatten a Celery beat schedule entry for policy scanning."""
    parts = [name, str(entry.get("task") or "")]
    kwargs = entry.get("kwargs")
    if kwargs:
        parts.append(str(kwargs))
    args = entry.get("args")
    if args:
        parts.append(str(args))
    return " ".join(parts).lower()


def forbidden_historical_schedule_hits(
    beat_schedule: dict[str, Any],
) -> list[str]:
    """Return beat keys that look like scheduled historical bootstrap / famous redownload."""
    hits: list[str] = []
    for name, entry in beat_schedule.items():
        if not isinstance(entry, dict):
            continue
        blob = beat_entry_text(str(name), entry)
        if any(token in blob for token in FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS):
            hits.append(str(name))
    return hits
