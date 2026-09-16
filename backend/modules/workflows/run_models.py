"""Durable workflow execution state (Phase 4). Independent of Celery TaskExecution."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowNodeRunStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Business-level orchestration run. TaskExecution remains Celery telemetry."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_workflow_runs_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_workflow_runs_tenant_definition",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_version_id"],
            ["workflow_versions.tenant_id", "workflow_versions.id"],
            name="fk_workflow_runs_tenant_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_workflow_runs_tenant_automation",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_workflow_runs_tenant_brand",
            ondelete="SET NULL",
        ),
        Index("ix_workflow_runs_tenant_id_status", "tenant_id", "status"),
        Index("ix_workflow_runs_tenant_id_started_at", "tenant_id", "started_at"),
        Index("ix_workflow_runs_tenant_id_automation_id", "tenant_id", "automation_id"),
        Index("ix_workflow_runs_tenant_id_correlation_id", "tenant_id", "correlation_id"),
        Index(
            "ix_workflow_runs_tenant_id_definition_id",
            "tenant_id",
            "workflow_definition_id",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    automation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    trigger_payload: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkflowRunStatus.QUEUED.value
    )
    context_snapshot: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class WorkflowNodeRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-node durable state for a WorkflowRun. May link to TaskExecution telemetry."""

    __tablename__ = "workflow_node_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workflow_run_id",
            "node_id",
            name="uq_workflow_node_runs_tenant_run_node",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            name="fk_workflow_node_runs_tenant_run",
            ondelete="CASCADE",
        ),
        Index("ix_workflow_node_runs_tenant_id_run_id", "tenant_id", "workflow_run_id"),
        Index("ix_workflow_node_runs_workflow_run_id_status", "workflow_run_id", "status"),
        Index("ix_workflow_node_runs_task_execution_id", "task_execution_id"),
        Index(
            "uq_workflow_node_runs_resume_token",
            "resume_token",
            unique=True,
            postgresql_where=text("resume_token IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(128), nullable=False)
    node_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkflowNodeRunStatus.PENDING.value
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    output_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    error_json: Mapped[dict[str, object] | None] = mapped_column(nullable=True)
    # Primary Celery telemetry link; additional IDs may be stored in task_execution_ids.
    task_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_executions.id", ondelete="SET NULL"), nullable=True
    )
    task_execution_ids: Mapped[list[str]] = mapped_column(default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    waiting_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resume_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
