from __future__ import annotations

import uuid
from datetime import date, datetime
from pydantic import BaseModel, HttpUrl


class RepoAssessmentSchema(BaseModel):
    what_it_does: str
    evidence: list[str]
    strongest_assets: list[str]
    main_limitations: list[str]
    best_commercial_angle: str
    confidence: str


class ProductIdeaMonetizationSchema(BaseModel):
    model: str
    pricing_logic: str
    estimated_willingness_to_pay: str


class ProductIdeaScoresSchema(BaseModel):
    revenue_potential: int
    customer_urgency: int
    repo_leverage: int
    speed_to_mvp: int
    competitive_intensity: int


class ProductIdeaSchema(BaseModel):
    rank: int
    title: str
    positioning: str
    target_customer: str
    pain_point: str
    product_concept: str
    why_this_repo_fits: str
    required_extensions: list[str]
    monetization: ProductIdeaMonetizationSchema
    scores: ProductIdeaScoresSchema
    time_to_mvp: str
    key_risks: list[str]
    why_now: str
    investor_angle: str
    v1_scope: list[str]
    not_for_v1: list[str]


class TrendingRepoResponse(BaseModel):
    id: uuid.UUID
    period: str
    snapshot_date: date
    github_id: int
    name: str
    full_name: str
    description: str | None
    html_url: str
    language: str | None
    topics: list[str]
    stars_count: int
    forks_count: int
    watchers_count: int
    open_issues_count: int
    stars_gained: int
    rank: int
    repo_assessment: RepoAssessmentSchema | None
    product_ideas: list[ProductIdeaSchema]
    ideas_generated_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrendingReposListResponse(BaseModel):
    repos: list[TrendingRepoResponse]
    period: str
    snapshot_date: date
    total: int


class GenerateIdeasRequest(BaseModel):
    """Request to trigger product-idea generation for a specific repo."""
    repo_id: uuid.UUID
