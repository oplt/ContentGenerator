"""§28 — concurrency + idempotency contracts for chess catalog operations.

Repeated-safe operations::

    same historical archive / famous catalog / provider window
    same game from two providers / same daily puzzle
    same analysis request / retry after worker failure

Desired outcomes (DB-backed where practical)::

    same game twice              → one ChessGame
    same game + new provider     → same ChessGame + new ChessGameSource
    same source twice            → no duplicate ChessGameSource
    same analysis profile twice  → reuse existing analysis job
    changed analysis profile     → new analysis job
"""

from __future__ import annotations

from dataclasses import dataclass

# Database guarantees that back §28 (not app-only checks).
DB_IDEMPOTENCY_GUARANTEES: tuple[str, ...] = (
    "uq_chess_games_tenant_id_game_fingerprint",
    "uq_chess_game_sources_tenant_provider_external",
    "uq_chess_puzzles_tenant_provider_external",
    "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
    "uq_chess_analysis_jobs_tenant_fingerprint_active",
    "uq_chess_provider_sync_tenant_provider_key",
)

# Application paths that must SAVEPOINT + retry on IntegrityError races.
RACE_SAFE_ENTRYPOINTS: tuple[str, ...] = (
    "ChessGameDedupeService.upsert_game",
    "ChessGameDedupeService._attach_source",
    "ChessAnalysisService._insert_or_reuse",
    "ChessCatalogService.sync_daily_puzzle",
)


@dataclass(frozen=True, slots=True)
class IdempotencyOutcome:
    """Documented result of a repeated operation."""

    operation: str
    expected: str


IDEMPOTENCY_OUTCOMES: tuple[IdempotencyOutcome, ...] = (
    IdempotencyOutcome("same_game_twice", "one ChessGame"),
    IdempotencyOutcome("same_game_new_provider", "same ChessGame + new ChessGameSource"),
    IdempotencyOutcome("same_source_twice", "no duplicate ChessGameSource"),
    IdempotencyOutcome("same_analysis_profile_twice", "reuse existing analysis/job"),
    IdempotencyOutcome("changed_analysis_profile", "new analysis"),
    IdempotencyOutcome("same_provider_window_retry", "checkpoint advances only on clean run"),
    IdempotencyOutcome("same_daily_puzzle", "one ChessPuzzle row per provider+external_id"),
    IdempotencyOutcome("worker_retry", "acks_late + unique indexes make redelivery safe"),
)


def uses_database_guarantees() -> bool:
    """Contract helper — §28 prefers unique indexes over SELECT-then-INSERT alone."""
    return True
