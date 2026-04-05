from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.modules.shared.schemas import ORMModel


class SendApprovalRequest(BaseModel):
    content_job_id: UUID
    recipient: str | None = None


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
    payload: dict[str, str]


class ApprovalRequestResponse(ORMModel):
    id: UUID
    content_job_id: UUID
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
    messages: list[ApprovalMessageResponse] = []
