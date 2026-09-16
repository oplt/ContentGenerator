"""Automation schemas (Phase 13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel


class AutomationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    workflow_definition_id: UUID
    workflow_version_id: UUID | None = None
    brand_id: UUID | None = None
    enabled: bool = False
    trigger_type: str = Field(default="manual", pattern="^(manual|schedule|webhook|event)$")
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str = Field(default="UTC", max_length=64)
    social_account_ids: list[UUID] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    # Explicit admin override — default strict BrandSocialAccount linkage.
    allow_unlinked_targets: bool = False


class AutomationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    workflow_version_id: UUID | None = None
    brand_id: UUID | None = None
    enabled: bool | None = None
    trigger_type: str | None = Field(default=None, pattern="^(manual|schedule|webhook|event)$")
    trigger_config: dict[str, Any] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    social_account_ids: list[UUID] | None = None
    settings: dict[str, Any] | None = None
    allow_unlinked_targets: bool = False


class AutomationTargetResponse(ORMModel):
    id: UUID
    social_account_id: UUID
    enabled: bool
    overrides_json: dict[str, Any]


class AutomationResponse(ORMModel):
    id: UUID
    tenant_id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    brand_id: UUID
    name: str
    enabled: bool
    trigger_type: str
    trigger_config: dict[str, Any]
    timezone: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    settings: dict[str, Any]
    webhook_endpoint_id: str | None = None
    created_at: datetime
    updated_at: datetime
    targets: list[AutomationTargetResponse] = Field(default_factory=list)


class BrandOptionResponse(BaseModel):
    id: UUID
    name: str
    niche: str | None = None
