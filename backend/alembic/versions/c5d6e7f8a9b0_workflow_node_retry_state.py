"""Persist WorkflowNodeRun last_error / error_class for durable retries.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-16 08:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_node_runs",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("error_class", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_workflow_node_runs_status_next_attempt_at",
        "workflow_node_runs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_node_runs_status_next_attempt_at",
        table_name="workflow_node_runs",
    )
    op.drop_column("workflow_node_runs", "error_class")
    op.drop_column("workflow_node_runs", "last_error")
