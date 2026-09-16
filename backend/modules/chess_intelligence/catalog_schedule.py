"""Chess catalog scheduling strategy (§11 / §26).

Reuse Celery beat + ``ChessCatalogJob`` only — no second scheduler.
Cadence is **configuration-driven**. Never schedule:

* daily redownload of all historical games
* daily reanalysis of all games
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from celery.schedules import crontab

from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJobKind
from backend.modules.chess_intelligence.historical_assets import (
    FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS,
    beat_entry_text,
)

Cadence = Literal["manual", "daily", "configurable", "on_demand"]


@dataclass(frozen=True, slots=True)
class CatalogOperationCadence:
    kind: str | None
    cadence: Cadence
    notes: str


# §26 recommended product behavior → existing infrastructure.
CATALOG_OPERATION_CADENCE: tuple[CatalogOperationCadence, ...] = (
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.PGN_IMPORT.value,
        cadence="manual",
        notes="Historical famous/archive corpus — bootstrap once; refresh when source changes",
    ),
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.PUZZLE_IMPORT.value,
        cadence="manual",
        notes="Bulk puzzle dump — filtered/capped import; never a warehouse schedule",
    ),
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.PROVIDER_SYNC.value,
        cadence="configurable",
        notes="Recent masters — daily default; optional every-N-minutes for active feeds",
    ),
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
        cadence="daily",
        notes="Daily puzzle — once/day + bounded Celery retries; GET stays local-first",
    ),
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.ENRICH_FAMOUS.value,
        cadence="manual",
        notes="After bootstrap/import or explicit catalog update — metadata only",
    ),
    CatalogOperationCadence(
        kind=ChessCatalogJobKind.EXTRACT_CRITICAL_MOMENTS.value,
        cadence="on_demand",
        notes="After Stockfish analysis completes",
    ),
    CatalogOperationCadence(
        kind=None,  # analyze_chess_game_task
        cadence="on_demand",
        notes="Stockfish — event-driven + analysis_fingerprint reuse; never bulk daily",
    ),
)

# Kinds that may appear on Celery beat (fanout → ChessCatalogJob).
SCHEDULED_JOB_KINDS: frozenset[str] = frozenset(
    {
        ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value,
        ChessCatalogJobKind.PROVIDER_SYNC.value,
    }
)

# Must never be auto-scheduled (historical / famous bootstrap).
MANUAL_ONLY_JOB_KINDS: frozenset[str] = frozenset(
    {
        ChessCatalogJobKind.PGN_IMPORT.value,
        ChessCatalogJobKind.PUZZLE_IMPORT.value,
        ChessCatalogJobKind.ENRICH_FAMOUS.value,
    }
)

# §26 — never auto-schedule bulk historical redownload or mass reanalysis.
FORBIDDEN_AUTO_SCHEDULE_TOKENS: frozenset[str] = frozenset(
    {
        *FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS,
        "reanalyze_all",
        "analyze_all",
        "bulk_reanalyze",
        "daily_reanalysis",
        "reanalysis_all_games",
        "stockfish_all",
        "analyze_every_game",
    }
)


def forbidden_auto_schedule_hits(beat_schedule: dict[str, Any]) -> list[str]:
    """Return beat keys that look like forbidden historical / bulk-reanalyze schedules."""
    hits: list[str] = []
    for name, entry in beat_schedule.items():
        if not isinstance(entry, dict):
            continue
        blob = beat_entry_text(str(name), entry)
        if any(token in blob for token in FORBIDDEN_AUTO_SCHEDULE_TOKENS):
            hits.append(str(name))
    return hits


def provider_sync_schedule(
    *,
    hour: int,
    minute: int,
    every_minutes: int | None,
) -> Any:
    """Daily crontab, or timedelta for optional tournament-frequency feeds."""
    if every_minutes is not None and every_minutes > 0:
        return timedelta(minutes=int(every_minutes))
    return crontab(hour=hour, minute=minute)


def build_chess_catalog_beat_schedule(
    *,
    daily_puzzle_enabled: bool,
    daily_puzzle_hour: int,
    daily_puzzle_minute: int,
    provider_sync_enabled: bool,
    provider_sync_hour: int,
    provider_sync_minute: int,
    provider_sync_every_minutes: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Config-driven beat entries. Empty when schedules disabled."""
    entries: dict[str, dict[str, Any]] = {}
    if daily_puzzle_enabled:
        entries["chess-daily-puzzle-sync"] = {
            "task": "backend.workers.tasks.chess_catalog_daily_puzzle_fanout_task",
            "schedule": crontab(hour=daily_puzzle_hour, minute=daily_puzzle_minute),
            "options": {"expires": 3_600},
        }
    if provider_sync_enabled:
        entries["chess-provider-sync-recent"] = {
            "task": "backend.workers.tasks.chess_catalog_provider_sync_fanout_task",
            "schedule": provider_sync_schedule(
                hour=provider_sync_hour,
                minute=provider_sync_minute,
                every_minutes=provider_sync_every_minutes,
            ),
            "options": {"expires": 7_200},
        }
    return entries
