"""Source poll scheduling helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.core.time_utils import as_utc, utc_now


def _ensure_utc(value: datetime) -> datetime:
    normalized = as_utc(value)
    if normalized is None:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized


def compute_next_poll_at(
    *,
    last_polled_at: datetime | None,
    polling_interval_minutes: int,
    now: datetime | None = None,
) -> datetime:
    """Return the next time an active source should be considered due."""
    current = now or utc_now()
    if last_polled_at is None:
        return current
    interval = max(int(polling_interval_minutes or 0), 1)
    return _ensure_utc(last_polled_at) + timedelta(minutes=interval)


def schedule_after_poll(
    *,
    polled_at: datetime,
    polling_interval_minutes: int,
) -> datetime:
    """Schedule the following poll after a completed attempt."""
    interval = max(int(polling_interval_minutes or 0), 1)
    return _ensure_utc(polled_at) + timedelta(minutes=interval)
