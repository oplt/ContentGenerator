"""Compute next_run_at for automation schedules (timezone-aware, DST-safe)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


def combine_local_wall_time(
    tz: ZoneInfo,
    day: date,
    hour: int,
    minute: int,
) -> datetime:
    """Map a local wall clock to a timezone-aware datetime.

    DST policy (documented):
    * **Nonexistent** (spring forward gap, e.g. 02:30 Europe/Brussels):
      advance minute-by-minute to the first valid local time after the gap.
    * **Ambiguous** (autumn overlap): prefer ``fold=0`` (the earlier occurrence).
    """
    probe = datetime(day.year, day.month, day.day, hour, minute)
    for _ in range(0, 180):  # up to 3h of gap walking
        cand = datetime(
            probe.year,
            probe.month,
            probe.day,
            probe.hour,
            probe.minute,
            tzinfo=tz,
            fold=0,
        )
        back = cand.astimezone(timezone.utc).astimezone(tz)
        if (
            back.year == probe.year
            and back.month == probe.month
            and back.day == probe.day
            and back.hour == probe.hour
            and back.minute == probe.minute
        ):
            # Ambiguous: fold=0 vs fold=1 differ in UTC — keep fold=0 (earlier).
            return cand
        probe += timedelta(minutes=1)
    raise ValueError(
        f"unable to resolve local wall time {day.isoformat()} {hour:02d}:{minute:02d} in {tz}"
    )


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
        day = local_after.date()
        candidate = combine_local_wall_time(tz, day, hour, minute)
        if candidate <= local_after:
            candidate = combine_local_wall_time(tz, day + timedelta(days=1), hour, minute)
        return candidate.astimezone(timezone.utc)

    if isinstance(cfg, WeeklyTriggerConfig):
        hour, minute = _parse_hhmm(cfg.at)
        wanted = {_WEEKDAY_INDEX[d] for d in cfg.days}
        for offset in range(0, 8):
            day = (local_after + timedelta(days=offset)).date()
            candidate = combine_local_wall_time(tz, day, hour, minute)
            if candidate.weekday() in wanted and candidate > local_after:
                return candidate.astimezone(timezone.utc)
        raise ValueError("unable to compute weekly next_run_at")

    # cron — croniter walks local wall times; normalize tz if naive.
    itr = croniter(cfg.expr, local_after)
    nxt_local = itr.get_next(datetime)
    if not isinstance(nxt_local, datetime):
        raise TypeError("croniter returned non-datetime")
    if nxt_local.tzinfo is None:
        nxt_local = combine_local_wall_time(
            tz, nxt_local.date(), nxt_local.hour, nxt_local.minute
        )
    return nxt_local.astimezone(timezone.utc)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_s, minute_s = value.split(":", 1)
    hour, minute = int(hour_s), int(minute_s)
    if hour > 23 or minute > 59:
        raise ValueError(f"invalid time '{value}'")
    return hour, minute
