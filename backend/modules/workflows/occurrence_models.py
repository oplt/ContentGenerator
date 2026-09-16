"""Durable scheduler occurrence models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationOccurrenceStatus(str, enum.Enum):
    CLAIMED = "claimed"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"


class AutomationOccurrence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Idempotent scheduled slot keyed by automation and occurrence."""

    __tablename__ = "automation_occurrences"
    __table_args__ = (
        UniqueConstraint(
            "automation_id",
            "scheduled_occurrence",
            name="uq_automation_occurrences_automation_occurrence",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_automation_occurrences_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_automation_occurrences_tenant_automation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            name="fk_automation_occurrences_tenant_workflow_run",
            ondelete="SET NULL",
        ),
        Index("ix_automation_occurrences_tenant_id_automation_id", "tenant_id", "automation_id"),
        Index("ix_automation_occurrences_tenant_id_status", "tenant_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_occurrence: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AutomationOccurrenceStatus.CLAIMED.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
