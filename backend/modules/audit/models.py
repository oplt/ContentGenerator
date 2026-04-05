from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, str]] = mapped_column(default=dict, nullable=False)
