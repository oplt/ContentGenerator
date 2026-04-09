from __future__ import annotations

from pydantic import BaseModel


class ChartPoint(BaseModel):
    label: str
    value: float
    secondary: float | None = None


class LearningLogEntry(BaseModel):
    category: str
    message: str
    weight: float | None = None
    recommendation: str | None = None


class AnalyticsOverviewResponse(BaseModel):
    summary: list[dict[str, str | float | int]]
    posts_over_time: list[ChartPoint]
    engagement_by_platform: list[ChartPoint]
    format_performance: list[ChartPoint]
    topic_performance: list[ChartPoint]
    publishing_funnel: list[ChartPoint]
    source_reliability: list[ChartPoint]
    hook_performance: list[ChartPoint]
    post_time_performance: list[ChartPoint]
    brand_performance: list[ChartPoint]
    topic_to_follower_conversion: list[ChartPoint]
    platform_comparison: list[ChartPoint]
    learning_log: list[LearningLogEntry]
