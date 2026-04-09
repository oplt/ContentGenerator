from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.modules.shared.schemas import ORMModel


class SendApprovalRequest(BaseModel):
    content_job_id: UUID | None = None
    recipient: str | None = None
    approval_type: str = "asset"
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    selected_platforms: list[str] = []
    scheduled_for: datetime | None = None


class ApprovalMessageResponse(ORMModel):
    id: UUID
    direction: str
    channel: str
    provider_message_id: str | None
    message_type: str
    raw_text: str | None
    parsed_intent: str
    intent_confidence: float
    user_feedback: str | None
    payload: dict[str, object]


class ApprovalRequestResponse(ORMModel):
    id: UUID
    content_job_id: UUID | None
    status: str
    channel: str
    recipient: str
    provider: str
    provider_request_id: str | None
    requested_at: datetime | None
    responded_at: datetime | None
    revision_count: int
    expires_at: datetime | None
    last_sent_at: datetime | None
    related_entity_type: str | None = None
    related_entity_id: str | None = None
    approval_type: str = "asset"
    buttons_json: list[str] = []
    telegram_message_id: str | None = None
    callback_verification_failures: int = 0
    callback_last_error: str | None = None
    responded_by: str | None = None
    risk_label: str | None = None
    response_payload_json: dict[str, object] = {}
    messages: list[ApprovalMessageResponse] = []


class ApprovalActionRequest(BaseModel):
    action: str
    feedback: str | None = None
