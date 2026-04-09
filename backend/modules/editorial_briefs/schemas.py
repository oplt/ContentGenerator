from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.modules.shared.schemas import ORMModel


class EditorialBriefResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    story_cluster_id: UUID
    brand_profile_id: UUID | None
    status: str
    headline: str
    why_now: str
    angle: str
    talking_points: list[str]
    recommended_format: str
    target_platforms: list[str]
    evidence_links: list[str]
    audience_segment: str
    platform_recommendations: list[str]
    tone_guidance: str
    cta_strategy: str
    caveats: list[str]
    suggested_formats: list[str]
    content_vertical: str
    risk_notes: str
    risk_level: str
    risk_label: str | None = None
    operator_note: str | None
    actioned_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BriefApproveRequest(BaseModel):
    operator_note: str | None = None


class BriefRejectRequest(BaseModel):
    operator_note: str


class BriefGenerateRequest(BaseModel):
    story_cluster_id: UUID
    brand_profile_id: UUID | None = None
    # Optional override TTL in hours (default: 24h)
    ttl_hours: int = 24


class BriefRewriteRequest(BaseModel):
    mode: str = "rewrite"
    operator_note: str | None = None
    requested_tone: str | None = None
    platform_mix: list[str] | None = None
    content_format: str | None = None
