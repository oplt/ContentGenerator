"""Daily puzzle hybrid helpers — local read + freshness metadata (§10)."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.modules.chess_intelligence.models import ChessPuzzle
from backend.modules.chess_intelligence.schemas import ChessDailyPuzzleResponse


def utc_day(*, now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%d")


def daily_puzzle_response(
    puzzle: ChessPuzzle,
    *,
    today_utc: str | None = None,
) -> ChessDailyPuzzleResponse:
    """Annotate a persisted daily puzzle with fresh/stale signals."""
    today = today_utc or utc_day()
    meta = dict(puzzle.source_metadata or {})
    daily_utc = meta.get("daily_utc")
    if not isinstance(daily_utc, str) or not daily_utc:
        daily_utc = None
    is_stale = daily_utc != today
    base = ChessDailyPuzzleResponse.model_validate(puzzle)
    return base.model_copy(
        update={
            "is_stale": is_stale,
            "freshness": "stale" if is_stale else "fresh",
            "daily_utc": daily_utc,
        }
    )
