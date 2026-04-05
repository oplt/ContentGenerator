from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.shared.schemas import ORMModel


class SocialAccountUpsertRequest(BaseModel):
    platform: str
    display_name: str
    handle: str | None = None
    account_external_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    scopes: list[str] = []
    metadata: dict[str, str] = {}
    use_stub: bool = True


class SocialAccountResponse(ORMModel):
    id: UUID
    platform: str
    display_name: str
    handle: str | None
    account_external_id: str | None
    status: str
    capability_flags: dict[str, str]
    metadata: dict[str, str]


class PublishNowRequest(BaseModel):
    content_job_id: UUID
    platforms: list[str] | None = None
    scheduled_for: datetime | None = None
    dry_run: bool = True
    idempotency_key: str | None = Field(default=None, min_length=8)


class PublishingJobResponse(ORMModel):
    id: UUID
    content_job_id: UUID
    social_account_id: UUID | None
    approval_request_id: UUID | None
    platform: str
    status: str
    provider: str
    idempotency_key: str
    dry_run: bool
    scheduled_for: datetime | None
    published_at: datetime | None
    retry_count: int
    failure_reason: str | None
    external_post_id: str | None
    external_post_url: str | None
    provider_payload: dict[str, str]


class PublishedPostResponse(ORMModel):
    id: UUID
    platform: str
    post_type: str
    external_post_id: str | None
    external_url: str | None
    status: str
    published_at: datetime | None
