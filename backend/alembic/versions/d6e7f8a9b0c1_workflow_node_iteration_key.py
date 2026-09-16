"""Add WorkflowNodeRun.iteration_key for real fan-out item executions.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-16 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_node_runs",
        sa.Column(
            "iteration_key",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
    )
    op.drop_constraint(
        "uq_workflow_node_runs_tenant_run_node",
        "workflow_node_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_workflow_node_runs_tenant_run_node_iter",
        "workflow_node_runs",
        ["tenant_id", "workflow_run_id", "node_id", "iteration_key"],
    )
    op.create_index(
        "ix_workflow_node_runs_run_node_iteration",
        "workflow_node_runs",
        ["workflow_run_id", "node_id", "iteration_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_node_runs_run_node_iteration",
        table_name="workflow_node_runs",
    )
    op.drop_constraint(
        "uq_workflow_node_runs_tenant_run_node_iter",
        "workflow_node_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_workflow_node_runs_tenant_run_node",
        "workflow_node_runs",
        ["tenant_id", "workflow_run_id", "node_id"],
    )
    op.drop_column("workflow_node_runs", "iteration_key")
