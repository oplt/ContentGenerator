from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, HttpUrl


class ProductIdeaSchema(BaseModel):
    title: str
    problem: str
    solution: str
    target_audience: str
    monetization: str
    wow_factor: str


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
    product_ideas: list[dict[str, Any]]
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
