"""Add workflow_runs + workflow_node_runs for durable orchestration state.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-16 00:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=True),
        sa.Column("trigger_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("trigger_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_workflow_runs_tenant_definition",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_version_id"],
            ["workflow_versions.tenant_id", "workflow_versions.id"],
            name="fk_workflow_runs_tenant_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_workflow_runs_tenant_automation",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_workflow_runs_tenant_brand",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workflow_runs_tenant_id_id"),
    )
    op.create_index(
        "ix_workflow_runs_tenant_id_status", "workflow_runs", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_workflow_runs_tenant_id_started_at", "workflow_runs", ["tenant_id", "started_at"]
    )
    op.create_index(
        "ix_workflow_runs_tenant_id_automation_id",
        "workflow_runs",
        ["tenant_id", "automation_id"],
    )
    op.create_index(
        "ix_workflow_runs_tenant_id_correlation_id",
        "workflow_runs",
        ["tenant_id", "correlation_id"],
    )
    op.create_index(
        "ix_workflow_runs_tenant_id_definition_id",
        "workflow_runs",
        ["tenant_id", "workflow_definition_id"],
    )

    op.create_table(
        "workflow_node_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=128), nullable=False),
        sa.Column("node_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("task_execution_id", sa.Uuid(), nullable=True),
        sa.Column("task_execution_ids", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waiting_reason", sa.String(length=128), nullable=True),
        sa.Column("resume_token", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            name="fk_workflow_node_runs_tenant_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_execution_id"],
            ["task_executions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_node_runs"),
        sa.UniqueConstraint(
            "tenant_id",
            "workflow_run_id",
            "node_id",
            name="uq_workflow_node_runs_tenant_run_node",
        ),
    )
    op.create_index(
        "ix_workflow_node_runs_tenant_id_run_id",
        "workflow_node_runs",
        ["tenant_id", "workflow_run_id"],
    )
    op.create_index(
        "ix_workflow_node_runs_workflow_run_id_status",
        "workflow_node_runs",
        ["workflow_run_id", "status"],
    )
    op.create_index(
        "ix_workflow_node_runs_task_execution_id",
        "workflow_node_runs",
        ["task_execution_id"],
    )
    op.create_index(
        "uq_workflow_node_runs_resume_token",
        "workflow_node_runs",
        ["resume_token"],
        unique=True,
        postgresql_where=sa.text("resume_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_node_runs_resume_token", table_name="workflow_node_runs")
    op.drop_index("ix_workflow_node_runs_task_execution_id", table_name="workflow_node_runs")
    op.drop_index(
        "ix_workflow_node_runs_workflow_run_id_status", table_name="workflow_node_runs"
    )
    op.drop_index("ix_workflow_node_runs_tenant_id_run_id", table_name="workflow_node_runs")
    op.drop_table("workflow_node_runs")

    op.drop_index("ix_workflow_runs_tenant_id_definition_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_tenant_id_correlation_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_tenant_id_automation_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_tenant_id_started_at", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_tenant_id_status", table_name="workflow_runs")
    op.drop_table("workflow_runs")
