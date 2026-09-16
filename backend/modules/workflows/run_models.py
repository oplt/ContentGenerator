"""Durable workflow execution state (Phase 4). Independent of Celery TaskExecution."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
        Index("ix_workflow_runs_tenant_id_created_at", "tenant_id", text("created_at DESC")),
        Index(
            "ix_workflow_runs_tenant_status_created_at",
            "tenant_id",
            "status",
            text("created_at DESC"),
        ),
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
            "iteration_key",
            name="uq_workflow_node_runs_tenant_run_node_iter",
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
            "ix_workflow_node_runs_status_claim_expires_at",
            "status",
            "claim_expires_at",
        ),
        Index(
            "ix_workflow_node_runs_ready_run_created_at",
            "workflow_run_id",
            "created_at",
            postgresql_where=text("status = 'ready'"),
        ),
        Index(
            "ix_workflow_node_runs_expired_claims",
            "claim_expires_at",
            postgresql_where=text(
                "status IN ('running', 'queued') AND claim_expires_at IS NOT NULL"
            ),
        ),
        Index(
            "ix_workflow_node_runs_finished_at_terminal",
            "finished_at",
            postgresql_where=text(
                "finished_at IS NOT NULL AND status IN "
                "('succeeded', 'failed', 'cancelled', 'skipped')"
            ),
        ),
        Index(
            "ix_workflow_node_runs_status_next_attempt_at",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_workflow_node_runs_run_node_iteration",
            "workflow_run_id",
            "node_id",
            "iteration_key",
        ),
        Index(
            "uq_workflow_node_runs_resume_token",
            "resume_token",
            unique=True,
            postgresql_where=text("resume_token IS NOT NULL"),
        ),
        Index(
            "uq_workflow_node_runs_claim_token",
            "claim_token",
            unique=True,
            postgresql_where=text("claim_token IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Empty string = non-iterated / placeholder; fan-out body uses immutable item keys.
    iteration_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
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
    # Durable worker claim lease (mirrors publishing job claiming).
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Cooperative cancel for QUEUED/RUNNING workers (Phase 16).
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class WorkflowWaitStatus(str, enum.Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class WorkflowWaitType(str, enum.Enum):
    DELAY = "delay"
    EVENT = "event"


class WorkflowWait(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Postgres-owned durable wait/delay deadline (Phase 5). Celery is a fast wake only."""

    __tablename__ = "workflow_waits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_workflow_waits_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            name="fk_workflow_waits_tenant_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workflow_node_run_id"],
            ["workflow_node_runs.id"],
            name="fk_workflow_waits_node_run",
            ondelete="CASCADE",
        ),
        Index("ix_workflow_waits_status_wake_at", "status", "wake_at"),
        Index("ix_workflow_waits_tenant_id_status", "tenant_id", "status"),
        Index(
            "ix_workflow_waits_pending_wake_at",
            "wake_at",
            postgresql_where=text("status = 'pending' AND wake_at IS NOT NULL"),
        ),
        Index(
            "uq_workflow_waits_resume_token_pending",
            "resume_token",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_workflow_waits_tenant_event_key_pending",
            "tenant_id",
            "event_key",
            unique=True,
            postgresql_where=text("status = 'pending' AND event_key IS NOT NULL"),
        ),
        Index("ix_workflow_waits_workflow_node_run_id", "workflow_node_run_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    workflow_node_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    resume_token: Mapped[str] = mapped_column(String(128), nullable=False)
    wait_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkflowWaitStatus.PENDING.value
    )
    timeout_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
