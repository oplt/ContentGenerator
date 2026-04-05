from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel


class BrandProfileUpsertRequest(BaseModel):
    name: str = Field(min_length=2)
    niche: str = "general"
    tone: str = "authoritative"
    audience: str = "General social audience"
    voice_notes: str | None = None
    preferred_platforms: list[str] = ["x", "bluesky", "instagram", "tiktok", "youtube"]
    default_cta: str | None = "Follow for more timely updates."
    hashtags_strategy: str = "balanced"
    risk_tolerance: str = "medium"
    require_whatsapp_approval: bool = True
    guardrails: dict[str, str] = {}
    visual_style: dict[str, str] = {}


class BrandProfileResponse(ORMModel):
    id: UUID
    name: str
    niche: str
    tone: str
    audience: str
    voice_notes: str | None
    preferred_platforms: list[str]
    default_cta: str | None
    hashtags_strategy: str
    risk_tolerance: str
    require_whatsapp_approval: bool
    guardrails: dict[str, str]
    visual_style: dict[str, str]


class CreateContentPlanRequest(BaseModel):
    story_cluster_id: UUID
    brand_profile_id: UUID | None = None


class ContentPlanResponse(ORMModel):
    id: UUID
    story_cluster_id: UUID
    brand_profile_id: UUID | None
    status: str
    decision: str
    content_format: str
    target_platforms: list[str]
    tone: str
    urgency: str
    risk_flags: list[str]
    recommended_cta: str | None
    hashtags_strategy: str
    approval_required: bool
    safe_to_publish: bool
    policy_trace: dict[str, str]
    scheduled_for: datetime | None
