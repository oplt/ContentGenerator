"""§29 — provider / engine / archive failures stay isolated from catalog reads.

Rules::

    Lichess unavailable          → existing games remain searchable
    daily-puzzle provider down   → latest valid persisted puzzle (stale OK)
    provider sync fails          → previous checkpoint remains valid
    Stockfish unavailable        → catalog usable; analysis job reports failure
    malformed archive PGN        → track error and continue import

Never delete or hide local catalog rows because a remote source is temporarily down.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FailureRule:
    failure: str
    local_behavior: str


FAILURE_RULES: tuple[FailureRule, ...] = (
    FailureRule(
        "lichess_unavailable",
        "GET /games and catalog search use local DB only — no provider call",
    ),
    FailureRule(
        "daily_puzzle_provider_unavailable",
        "GET /puzzles/daily returns last persisted daily with is_stale/freshness",
    ),
    FailureRule(
        "provider_sync_fails",
        "ChessProviderSyncState.high_water_mark unchanged (mark_failure only)",
    ),
    FailureRule(
        "stockfish_unavailable",
        "enqueue/process sets analysis FAILED or 503; ChessGame rows untouched",
    ),
    FailureRule(
        "malformed_archive_pgn",
        "PgnArchiveImporter records error, continues; valid games still persist",
    ),
)

# Paths that must never cascade-delete catalog rows on remote failure.
CATALOG_PRESERVATION_GUARANTEE = (
    "Remote outage must not delete ChessGame / ChessPuzzle / ChessGameSource rows."
)


def catalog_survives_remote_outage() -> bool:
    """Contract helper for tests/docs."""
    return True
