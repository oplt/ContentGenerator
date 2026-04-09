from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.modules.shared.schemas import ORMModel


class GenerateContentRequest(BaseModel):
    content_plan_id: UUID


class RegenerateContentRequest(BaseModel):
    feedback: str


class RegenerateAssetGroupRequest(BaseModel):
    instruction: str


class GeneratedAssetResponse(ORMModel):
    id: UUID
    asset_type: str
    platform: str | None
    variant_label: str | None
    public_url: str | None
    mime_type: str
    metadata: dict[str, str]
    source_trace: dict[str, str]
    text_content: str | None


class ContentJobResponse(ORMModel):
    id: UUID
    content_plan_id: UUID
    revision_of_job_id: UUID | None
    job_type: str
    status: str
    stage: str
    progress: float
    feedback: str | None
    error_message: str | None
    risk_label: str | None = None
    risk_review: dict[str, object] = {}
    started_at: datetime | None
    completed_at: datetime | None
    assets: list[GeneratedAssetResponse] = []
