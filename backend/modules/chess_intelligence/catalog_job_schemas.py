"""API contracts for chess catalog async jobs (Phase 24)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ChessCatalogJobKindLiteral = Literal[
    "pgn_import",
    "puzzle_import",
    "daily_puzzle_sync",
    "enrich_famous",
    "extract_critical_moments",
    "provider_sync",
]


class ChessCatalogJobCreateRequest(BaseModel):
    kind: ChessCatalogJobKindLiteral
    params: dict[str, Any] = Field(default_factory=dict)
    import_batch_id: str | None = None


class ChessCatalogJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    kind: str
    status: str
    progress: float
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    celery_task_id: str | None = None
    import_batch_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChessProviderSyncStateResponse(BaseModel):
    """§33 inspect — durable feed checkpoint (not a job run)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    provider: str
    sync_key: str
    query_hash: str
    cursor: str | None = None
    high_water_mark: datetime | None = None
    lookback_seconds: int
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_job_id: UUID | None = None
    last_error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ChessProviderSyncStateListResponse(BaseModel):
    items: list[ChessProviderSyncStateResponse]
