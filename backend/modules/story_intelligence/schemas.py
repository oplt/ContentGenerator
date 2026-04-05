from __future__ import annotations

from datetime import datetime
from uuid import UUID

from backend.modules.shared.schemas import ORMModel, SummaryMetric


class NormalizedArticleResponse(ORMModel):
    id: UUID
    raw_article_id: UUID
    title: str
    summary: str | None
    body: str
    canonical_url: str
    source_name: str
    language: str
    published_at: datetime | None
    keywords: list[str]
    topic_tags: list[str]
    entities: list[str]
    credibility_score: float
    freshness_score: float
    worthiness_score: float
    explainability: dict[str, str]


class TrendScoreResponse(ORMModel):
    id: UUID
    story_cluster_id: UUID
    score: float
    freshness_score: float
    credibility_score: float
    momentum_score: float
    worthiness_score: float
    explanation: dict[str, str]


class StoryClusterResponse(ORMModel):
    id: UUID
    slug: str
    headline: str
    summary: str
    primary_topic: str
    article_count: int
    trend_direction: str
    worthy_for_content: bool
    risk_level: str
    explainability: dict[str, str]
    latest_trend_score: float | None = None


class StoryClusterDetailResponse(StoryClusterResponse):
    articles: list[NormalizedArticleResponse]
    trend_score: TrendScoreResponse | None = None


class ContentWorthinessDecision(ORMModel):
    cluster_id: UUID
    decision: str
    score: float
    reasons: list[str]


class TrendDashboardResponse(ORMModel):
    summary: list[SummaryMetric]
    clusters: list[StoryClusterResponse]
