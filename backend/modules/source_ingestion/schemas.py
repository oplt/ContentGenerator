from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel


class SourceCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    source_type: str
    url: str
    parser_type: str = "auto"
    category: str = "general"
    config: dict[str, str] = {}
    polling_interval_minutes: int = Field(default=30, ge=5, le=1440)
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0)
    active: bool = True


class SourceUpdateRequest(BaseModel):
    name: str | None = None
    parser_type: str | None = None
    category: str | None = None
    config: dict[str, str] | None = None
    polling_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    trust_score: float | None = Field(default=None, ge=0.0, le=1.0)
    active: bool | None = None


class SourceResponse(ORMModel):
    id: UUID
    name: str
    source_type: str
    url: str
    parser_type: str
    category: str
    config: dict[str, str]
    polling_interval_minutes: int
    trust_score: float
    active: bool
    failure_count: int
    success_count: int
    circuit_state: str
    last_polled_at: datetime | None
    last_success_at: datetime | None


class SourceFetchRunResponse(ORMModel):
    id: UUID
    source_id: UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    http_status: int | None
    duration_ms: int | None
    articles_found: int
    new_articles: int
    error_message: str | None


class RawArticleResponse(ORMModel):
    id: UUID
    source_id: UUID
    title: str
    summary: str | None
    canonical_url: str
    author: str | None
    language: str | None
    published_at: datetime | None
    extraction_confidence: float


class SourceHealthResponse(ORMModel):
    source_id: UUID
    status: str
    failure_count: int
    success_count: int
    circuit_state: str
    negative_cache_until: datetime | None
    last_success_at: datetime | None


class IngestionTriggerResponse(BaseModel):
    source_id: UUID
    status: str
    raw_articles_ingested: int
    clusters_updated: int


class CatalogEntryResponse(BaseModel):
    id: str
    name: str
    url: str
    source_type: str
    category: str
    description: str
    trust_score: float
    polling_interval_minutes: int
