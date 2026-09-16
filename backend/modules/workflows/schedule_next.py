"""Compute next_run_at for automation schedules (timezone-aware)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from backend.modules.workflows.schedule_config import (
    CronTriggerConfig,
    DailyTriggerConfig,
    IntervalTriggerConfig,
    TriggerConfig,
    WeeklyTriggerConfig,
    parse_trigger_config,
)

_WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone '{name}'") from exc


def occurrence_key(scheduled_for: datetime) -> str:
    """Stable unique key for UNIQUE(automation_id, scheduled_occurrence)."""
    utc = scheduled_for.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_next_run_at(
    *,
    trigger_config: dict[str, object] | TriggerConfig,
    timezone_name: str,
    after: datetime | None = None,
) -> datetime:
    """Return next fire time as UTC-aware datetime strictly after ``after``."""
    cfg = (
        trigger_config
        if isinstance(
            trigger_config,
            (IntervalTriggerConfig, DailyTriggerConfig, WeeklyTriggerConfig, CronTriggerConfig),
        )
        else parse_trigger_config(dict(trigger_config))
    )
    tz = resolve_tz(timezone_name)
    base = after or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    local_after = base.astimezone(tz)

    if isinstance(cfg, IntervalTriggerConfig):
        nxt = base + timedelta(seconds=cfg.every_seconds)
        return nxt.astimezone(timezone.utc)

    if isinstance(cfg, DailyTriggerConfig):
        hour, minute = _parse_hhmm(cfg.at)
        candidate = local_after.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_after:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    if isinstance(cfg, WeeklyTriggerConfig):
        hour, minute = _parse_hhmm(cfg.at)
        wanted = {_WEEKDAY_INDEX[d] for d in cfg.days}
        for offset in range(0, 8):
            day = local_after + timedelta(days=offset)
            candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate.weekday() in wanted and candidate > local_after:
                return candidate.astimezone(timezone.utc)
        raise ValueError("unable to compute weekly next_run_at")

    # cron
    itr = croniter(cfg.expr, local_after)
    nxt_local = itr.get_next(datetime)
    if not isinstance(nxt_local, datetime):
        raise TypeError("croniter returned non-datetime")
    if nxt_local.tzinfo is None:
        nxt_local = nxt_local.replace(tzinfo=tz)
    return nxt_local.astimezone(timezone.utc)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_s, minute_s = value.split(":", 1)
    hour, minute = int(hour_s), int(minute_s)
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time '{value}'")
    return hour, minute
