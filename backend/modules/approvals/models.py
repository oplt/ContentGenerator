from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalIntent(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"
    UNKNOWN = "unknown"


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_tenant_id_status", "tenant_id", "status"),
        Index(
            "ix_approval_requests_tenant_id_status_type_expires_at",
            "tenant_id",
            "status",
            "approval_type",
            "expires_at",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    content_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_jobs.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(String(32), nullable=False, default="pending")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    recipient: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="stub")
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_type: Mapped[str] = mapped_column(String(32), nullable=False, default="asset")
    buttons_json: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    # Telegram message_id of the approval card — stored so it can be edited in-place after action
    telegram_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    callback_verification_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    callback_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_payload_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


class ApprovalMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_messages"
    __table_args__ = (Index("ix_approval_messages_approval_request_id", "approval_request_id"),)

    approval_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="whatsapp")
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_intent: Mapped[ApprovalIntent] = mapped_column(String(32), nullable=False, default="unknown")
    intent_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    user_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


class WebhookInbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhooks_inbox"
    __table_args__ = (Index("ix_webhooks_inbox_provider_received_at", "provider", "received_at"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
