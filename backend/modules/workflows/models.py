"""Workflow definition, versioning, and automation binding models (Phase 1)."""

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

from backend.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin


class WorkflowDefinitionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class AutomationTriggerType(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"
    EVENT = "event"


class WorkflowDefinition(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    """Reusable workflow template (mutable shell; graphs live on WorkflowVersion)."""

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_workflow_definitions_tenant_id_slug"),
        UniqueConstraint("tenant_id", "id", name="uq_workflow_definitions_tenant_id_id"),
        Index("ix_workflow_definitions_tenant_id_status", "tenant_id", "status"),
        Index(
            "ix_workflow_definitions_tenant_updated_at_alive",
            "tenant_id",
            text("updated_at DESC"),
            postgresql_where=(SoftDeleteMixin.deleted_at.is_(None)),
        ),
        ForeignKeyConstraint(
            ["tenant_id", "id", "current_version_id"],
            [
                "workflow_versions.tenant_id",
                "workflow_versions.workflow_definition_id",
                "workflow_versions.id",
            ],
            name="fk_workflow_definitions_current_version_composite",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=WorkflowDefinitionStatus.DRAFT.value
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class WorkflowVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable published (or draft) snapshot of a workflow graph.

    Once ``published_at`` is set, rows must not be mutated by application code.
    Does not use VersionMixin: ``version`` is the product version number, not ORM
    optimistic locking.
    """

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "workflow_definition_id",
            "version",
            name="uq_workflow_versions_tenant_definition_version",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_workflow_versions_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "workflow_definition_id",
            "id",
            name="uq_workflow_versions_tenant_definition_id",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_workflow_versions_tenant_definition",
            ondelete="CASCADE",
        ),
        Index(
            "ix_workflow_versions_tenant_id_definition_id",
            "tenant_id",
            "workflow_definition_id",
        ),
        Index("ix_workflow_versions_tenant_id_published_at", "tenant_id", "published_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    input_schema_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    output_schema_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, Base):
    """Binds a workflow version to a brand, trigger, and account targets."""

    __tablename__ = "automations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_automations_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_automations_tenant_workflow_definition",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id", "workflow_version_id"],
            [
                "workflow_versions.tenant_id",
                "workflow_versions.workflow_definition_id",
                "workflow_versions.id",
            ],
            name="fk_automations_tenant_definition_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_automations_tenant_brand",
            ondelete="CASCADE",
        ),
        Index("ix_automations_tenant_id_enabled", "tenant_id", "enabled"),
        Index("ix_automations_tenant_id_brand_id", "tenant_id", "brand_id"),
        Index(
            "ix_automations_tenant_id_workflow_definition_id",
            "tenant_id",
            "workflow_definition_id",
        ),
        Index("ix_automations_tenant_id_next_run_at", "tenant_id", "next_run_at"),
        Index(
            "uq_automations_webhook_endpoint_id",
            "webhook_endpoint_id",
            unique=True,
            postgresql_where=text("webhook_endpoint_id IS NOT NULL"),
        ),
        Index(
            "ix_automations_tenant_updated_at_alive",
            "tenant_id",
            text("updated_at DESC"),
            postgresql_where=(SoftDeleteMixin.deleted_at.is_(None)),
        ),
        Index(
            "ix_automations_due_schedule_next_run_at",
            "next_run_at",
            postgresql_where=text(
                "enabled IS TRUE AND trigger_type = 'schedule' "
                "AND deleted_at IS NULL AND next_run_at IS NOT NULL"
            ),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trigger_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AutomationTriggerType.MANUAL.value
    )
    trigger_config: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)
    # Public opaque id for POST /workflows/webhooks/{endpoint_id} (Phase 17).
    webhook_endpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AutomationTarget(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Destination social account for an automation run."""

    __tablename__ = "automation_targets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "automation_id",
            "social_account_id",
            name="uq_automation_targets_tenant_automation_account",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_automation_targets_tenant_automation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "social_account_id"],
            ["social_accounts.tenant_id", "social_accounts.id"],
            name="fk_automation_targets_tenant_social_account",
            ondelete="CASCADE",
        ),
        Index("ix_automation_targets_tenant_id_automation_id", "tenant_id", "automation_id"),
        Index(
            "ix_automation_targets_tenant_id_social_account_id",
            "tenant_id",
            "social_account_id",
        ),
        Index(
            "ix_automation_targets_tenant_id_enabled",
            "tenant_id",
            "enabled",
            postgresql_where=(SoftDeleteMixin.deleted_at.is_(None)),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    social_account_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    overrides_json: Mapped[dict[str, object]] = mapped_column(default=dict, nullable=False)


from backend.modules.workflows.occurrence_models import (  # noqa: E402
    AutomationOccurrence,
    AutomationOccurrenceStatus,
)

# Phase 4 execution state (imported so model_registry picks them up via this module).
from backend.modules.workflows.run_models import (  # noqa: E402
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowWait,
    WorkflowWaitStatus,
    WorkflowWaitType,
)

__all__ = [
    "Automation",
    "AutomationOccurrence",
    "AutomationOccurrenceStatus",
    "AutomationTarget",
    "AutomationTriggerType",
    "WorkflowDefinition",
    "WorkflowDefinitionStatus",
    "WorkflowNodeRun",
    "WorkflowNodeRunStatus",
    "WorkflowRun",
    "WorkflowRunStatus",
    "WorkflowVersion",
    "WorkflowWait",
    "WorkflowWaitStatus",
    "WorkflowWaitType",
]
