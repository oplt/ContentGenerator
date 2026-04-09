from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

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
    content_vertical: str
    source_tier: str
    explainability: dict[str, str]


class TrendScoreResponse(ORMModel):
    id: UUID
    story_cluster_id: UUID
    score: float
    freshness_score: float
    credibility_score: float
    momentum_score: float
    worthiness_score: float
    velocity_score: float
    cross_source_score: float
    audience_fit_score: float = 0.0
    novelty_score: float = 0.0
    monetization_score: float = 0.0
    risk_penalty_score: float = 0.0
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
    workflow_state: str
    content_vertical: str
    risk_flags: list[str]
    tier1_sources_confirmed: int
    awaiting_confirmation: bool
    block_reason: str | None = None
    explainability: dict[str, str]
    review_risk_label: str | None = None
    review_reasons: list[str] = []
    latest_trend_score: float | None = None


class StoryClusterDetailResponse(StoryClusterResponse):
    articles: list[NormalizedArticleResponse]
    trend_score: TrendScoreResponse | None = None


class ContentWorthinessDecision(ORMModel):
    cluster_id: UUID
    decision: str
    score: float
    reasons: list[str]


class TrendCandidateResponse(ORMModel):
    id: UUID
    story_cluster_id: UUID
    date_bucket: date
    primary_topic: str
    subtopics: list[str]
    supporting_item_ids: list[str]
    evidence_links: list[str]
    extracted_claims: list[str]
    cross_source_count: int
    source_mix: dict[str, object]
    velocity_score: float
    recency_score: float
    novelty_score: float
    audience_fit_score: float
    monetization_score: float
    risk_score: float
    final_score: float
    status: str
    expires_at: datetime | None
    score_explanation: dict[str, object]


class TrendCandidateActionRequest(BaseModel):
    action: str
    operator_note: str | None = None


class TrendDashboardResponse(ORMModel):
    summary: list[SummaryMetric]
    clusters: list[StoryClusterResponse]
