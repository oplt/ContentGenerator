"""Add workflow_waits for durable delay/event deadlines (Phase 5).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-16 09:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_waits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_node_run_id", sa.Uuid(), nullable=False),
        sa.Column("resume_token", sa.String(length=128), nullable=False),
        sa.Column("wait_type", sa.String(length=32), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=True),
        sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("timeout_action", sa.String(length=32), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_outcome", sa.String(length=32), nullable=True),
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
            name="fk_workflow_waits_tenant_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_node_run_id"],
            ["workflow_node_runs.id"],
            name="fk_workflow_waits_node_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_waits"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workflow_waits_tenant_id_id"),
    )
    op.create_index(
        "ix_workflow_waits_status_wake_at",
        "workflow_waits",
        ["status", "wake_at"],
    )
    op.create_index(
        "ix_workflow_waits_tenant_id_status",
        "workflow_waits",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_workflow_waits_workflow_node_run_id",
        "workflow_waits",
        ["workflow_node_run_id"],
    )
    op.create_index(
        "uq_workflow_waits_resume_token_pending",
        "workflow_waits",
        ["resume_token"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_workflow_waits_tenant_event_key_pending",
        "workflow_waits",
        ["tenant_id", "event_key"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND event_key IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND event_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_waits_tenant_event_key_pending", table_name="workflow_waits")
    op.drop_index("uq_workflow_waits_resume_token_pending", table_name="workflow_waits")
    op.drop_index("ix_workflow_waits_workflow_node_run_id", table_name="workflow_waits")
    op.drop_index("ix_workflow_waits_tenant_id_status", table_name="workflow_waits")
    op.drop_index("ix_workflow_waits_status_wake_at", table_name="workflow_waits")
    op.drop_table("workflow_waits")
