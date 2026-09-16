"""Schedule trigger_config schema (Phase 7)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IntervalTriggerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["interval"] = "interval"
    every_seconds: int = Field(ge=60, le=86_400 * 30)


class DailyTriggerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["daily"] = "daily"
    at: str = Field(pattern=r"^\d{2}:\d{2}$")


class WeeklyTriggerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["weekly"] = "weekly"
    days: list[str] = Field(min_length=1)
    at: str = Field(pattern=r"^\d{2}:\d{2}$")

    @field_validator("days")
    @classmethod
    def _normalize_days(cls, value: list[str]) -> list[str]:
        allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        normalized: list[str] = []
        for day in value:
            key = day.strip().lower()[:3]
            if key not in allowed:
                raise ValueError(f"invalid weekday '{day}'")
            if key not in normalized:
                normalized.append(key)
        if not normalized:
            raise ValueError("days must not be empty")
        return normalized


class CronTriggerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["cron"] = "cron"
    expr: str = Field(min_length=5, max_length=128)


TriggerConfig = IntervalTriggerConfig | DailyTriggerConfig | WeeklyTriggerConfig | CronTriggerConfig


class TriggerConfigEnvelope(BaseModel):
    """Accepts kind/type alias and dispatches to a concrete trigger config."""

    model_config = ConfigDict(extra="allow")

    kind: str | None = None
    type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _alias_type(cls, value: Any) -> Any:
        if isinstance(value, dict):
            data = dict(value)
            if "kind" not in data and "type" in data:
                data["kind"] = data["type"]
            return data
        return value


def parse_trigger_config(raw: dict[str, Any] | None) -> TriggerConfig:
    payload = dict(raw or {})
    envelope = TriggerConfigEnvelope.model_validate(payload)
    kind = (envelope.kind or "").strip().lower()
    if kind == "interval":
        return IntervalTriggerConfig.model_validate(payload)
    if kind == "daily":
        return DailyTriggerConfig.model_validate(payload)
    if kind == "weekly":
        return WeeklyTriggerConfig.model_validate(payload)
    if kind == "cron":
        return CronTriggerConfig.model_validate(payload)
    raise ValueError(f"unsupported trigger kind '{kind or 'missing'}'")
