"""Add workflow query indexes for list + scheduler access patterns.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-16 07:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Definitions list: tenant + alive + ORDER BY updated_at DESC
    op.create_index(
        "ix_workflow_definitions_tenant_updated_at_alive",
        "workflow_definitions",
        ["tenant_id", sa.text("updated_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_workflow_definitions_tenant_id_enabled", table_name="workflow_definitions")

    # Automations list: tenant + alive + ORDER BY updated_at DESC
    op.create_index(
        "ix_automations_tenant_updated_at_alive",
        "automations",
        ["tenant_id", sa.text("updated_at DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Scheduler claim: due schedule rows ordered by next_run_at
    op.create_index(
        "ix_automations_due_schedule_next_run_at",
        "automations",
        ["next_run_at"],
        unique=False,
        postgresql_where=sa.text(
            "enabled IS TRUE AND trigger_type = 'schedule' "
            "AND deleted_at IS NULL AND next_run_at IS NOT NULL"
        ),
    )
    op.drop_index("ix_automations_enabled_next_run_at", table_name="automations")

    # Runs list: tenant + ORDER BY created_at DESC LIMIT n
    op.create_index(
        "ix_workflow_runs_tenant_id_created_at",
        "workflow_runs",
        ["tenant_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_tenant_id_created_at", table_name="workflow_runs")

    op.create_index(
        "ix_automations_enabled_next_run_at",
        "automations",
        ["enabled", "next_run_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_automations_due_schedule_next_run_at", table_name="automations")
    op.drop_index("ix_automations_tenant_updated_at_alive", table_name="automations")

    op.create_index(
        "ix_workflow_definitions_tenant_id_enabled",
        "workflow_definitions",
        ["tenant_id", "deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(
        "ix_workflow_definitions_tenant_updated_at_alive",
        table_name="workflow_definitions",
    )
