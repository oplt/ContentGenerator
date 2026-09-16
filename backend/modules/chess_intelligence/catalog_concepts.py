"""Three separate catalog concepts — do not overload ``is_famous``.

| Concept | Meaning | Storage |
|---------|---------|---------|
| Historical / Famous | durable editorial significance | ``ChessGame.is_famous`` (+ title/tags) |
| Recent / Notable | newly discovered / worth inspecting | **derived** (no boolean column) |
| Content Opportunity | algorithmic content suitability | ``ChessContentOpportunityScore`` |

Famous ≠ recent ≠ high opportunity. A 1851 immortal can be famous with low
\"recent\" signal; yesterday's masters game can be recent/notable with a high
opportunity score without being famous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from backend.modules.chess_intelligence.ingestion_mode import (
    METADATA_KEY,
    ChessIngestionMode,
)
from backend.modules.chess_intelligence.provider_sync_state import parse_game_date

# Product window for \"recent\" discovery / play.
DEFAULT_RECENT_DAYS = 14

# Classic cutoff: famous games older than this are never labeled recent/notable.
FAMOUS_RECENT_YEAR_FLOOR = 1990

_NOTABLE_EVENT_TOKENS = (
    "candidates",
    "world championship",
    "world cup",
    "olympiad",
    "sinquefield",
    "tata steel",
    "norway chess",
    "grand prix",
    "superbet",
)


@dataclass(frozen=True, slots=True)
class GameConceptFlags:
    """Derived presentation flags — never persist ``is_notable`` / ``is_recent``."""

    is_famous: bool
    is_recent: bool
    is_notable: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def derive_is_recent(
    *,
    is_famous: bool,
    year: int | None,
    game_date: str | None,
    created_at: datetime | None,
    source_metadata: dict[str, Any] | None,
    now: datetime | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> bool:
    """True when the game is newly played or newly discovered — not a dusty classic."""
    current = _as_aware(now) or _utcnow()
    # Famous deep history stays \"historical\", even if the row was just curated.
    if is_famous and year is not None and year < FAMOUS_RECENT_YEAR_FLOOR:
        return False

    meta = source_metadata or {}
    if meta.get(METADATA_KEY) == ChessIngestionMode.RECENT_DISCOVERY.value:
        return True

    played = parse_game_date(game_date)
    if played is not None and played >= current - timedelta(days=recent_days):
        return True

    created = _as_aware(created_at)
    if (
        created is not None
        and created >= current - timedelta(days=recent_days)
        and not is_famous
    ):
        return True
    return False


def _event_looks_notable(event: str | None) -> bool:
    if not event:
        return False
    lowered = event.lower()
    return any(token in lowered for token in _NOTABLE_EVENT_TOKENS)


def derive_is_notable(
    *,
    is_famous: bool,
    is_recent: bool,
    white_rating: int | None = None,
    black_rating: int | None = None,
    event: str | None = None,
    historical_tags: Sequence[str] | None = None,
    content_opportunity_score: int | None = None,
    critical_moment_count: int = 0,
) -> bool:
    """Derive notable (worth inspecting) — prefer this over a permanent boolean.

    Famous-only classics are not \"notable\" in the recent/notable sense unless
    also recent. Uses ratings, event, content score, moments, editorial tags.
    """
    tags = {t.lower() for t in (historical_tags or [])}
    if "notable" in tags or "recent_notable" in tags:
        return True

    # Historical fame alone must not equal notable.
    if is_famous and not is_recent:
        return False

    points = 0
    if is_recent:
        points += 2
    ratings = [r for r in (white_rating, black_rating) if r is not None]
    if ratings and max(ratings) >= 2600:
        points += 2
    elif ratings and max(ratings) >= 2400:
        points += 1
    if _event_looks_notable(event):
        points += 2
    if content_opportunity_score is not None and content_opportunity_score >= 55:
        points += 2
    elif content_opportunity_score is not None and content_opportunity_score >= 40:
        points += 1
    if critical_moment_count > 0:
        points += 1
    return points >= 3


def classify_game(
    *,
    is_famous: bool,
    year: int | None = None,
    game_date: str | None = None,
    created_at: datetime | None = None,
    source_metadata: dict[str, Any] | None = None,
    white_rating: int | None = None,
    black_rating: int | None = None,
    event: str | None = None,
    historical_tags: Sequence[str] | None = None,
    content_opportunity_score: int | None = None,
    critical_moment_count: int = 0,
    now: datetime | None = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
) -> GameConceptFlags:
    """Compute the three orthogonal signals for one catalog game."""
    famous = bool(is_famous)
    recent = derive_is_recent(
        is_famous=famous,
        year=year,
        game_date=game_date,
        created_at=created_at,
        source_metadata=source_metadata,
        now=now,
        recent_days=recent_days,
    )
    notable = derive_is_notable(
        is_famous=famous,
        is_recent=recent,
        white_rating=white_rating,
        black_rating=black_rating,
        event=event,
        historical_tags=historical_tags,
        content_opportunity_score=content_opportunity_score,
        critical_moment_count=critical_moment_count,
    )
    return GameConceptFlags(is_famous=famous, is_recent=recent, is_notable=notable)


def classify_orm_game(
    game: Any,
    *,
    content_opportunity_score: int | None = None,
    critical_moment_count: int = 0,
    now: datetime | None = None,
) -> GameConceptFlags:
    """Classify a ``ChessGame`` ORM/row-like object."""
    return classify_game(
        is_famous=bool(getattr(game, "is_famous", False)),
        year=getattr(game, "year", None),
        game_date=getattr(game, "game_date", None),
        created_at=getattr(game, "created_at", None),
        source_metadata=getattr(game, "source_metadata", None) or {},
        white_rating=getattr(game, "white_rating", None),
        black_rating=getattr(game, "black_rating", None),
        event=getattr(game, "event", None),
        historical_tags=getattr(game, "historical_tags", None) or [],
        content_opportunity_score=content_opportunity_score,
        critical_moment_count=critical_moment_count,
        now=now,
    )
