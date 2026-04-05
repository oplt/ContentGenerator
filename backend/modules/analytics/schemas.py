from __future__ import annotations

from pydantic import BaseModel


class ChartPoint(BaseModel):
    label: str
    value: float
    secondary: float | None = None


class AnalyticsOverviewResponse(BaseModel):
    summary: list[dict[str, str | float | int]]
    posts_over_time: list[ChartPoint]
    engagement_by_platform: list[ChartPoint]
    format_performance: list[ChartPoint]
    topic_performance: list[ChartPoint]
    publishing_funnel: list[ChartPoint]
    source_reliability: list[ChartPoint]
