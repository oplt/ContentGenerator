"""Add automation_occurrences for scheduler idempotency (Phase 7).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-16 00:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "automation_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_occurrence", sa.String(length=64), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="claimed"),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_automation_occurrences_tenant_automation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_run_id"],
            ["workflow_runs.tenant_id", "workflow_runs.id"],
            name="fk_automation_occurrences_tenant_workflow_run",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "automation_id",
            "scheduled_occurrence",
            name="uq_automation_occurrences_automation_occurrence",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_automation_occurrences_tenant_id_id",
        ),
    )
    op.create_index(
        "ix_automation_occurrences_tenant_id_automation_id",
        "automation_occurrences",
        ["tenant_id", "automation_id"],
    )
    op.create_index(
        "ix_automation_occurrences_tenant_id_status",
        "automation_occurrences",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_occurrences_tenant_id_status",
        table_name="automation_occurrences",
    )
    op.drop_index(
        "ix_automation_occurrences_tenant_id_automation_id",
        table_name="automation_occurrences",
    )
    op.drop_table("automation_occurrences")
