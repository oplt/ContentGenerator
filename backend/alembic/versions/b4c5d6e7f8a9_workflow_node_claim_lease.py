"""Add WorkflowNodeRun claim lease columns for durable one-node execution.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-16 08:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workflow_node_runs",
        sa.Column("claim_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("worker_task_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workflow_node_runs",
        sa.Column("execution_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_workflow_node_runs_status_claim_expires_at",
        "workflow_node_runs",
        ["status", "claim_expires_at"],
    )
    op.create_index(
        "uq_workflow_node_runs_claim_token",
        "workflow_node_runs",
        ["claim_token"],
        unique=True,
        postgresql_where=sa.text("claim_token IS NOT NULL"),
        sqlite_where=sa.text("claim_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_node_runs_claim_token", table_name="workflow_node_runs")
    op.drop_index(
        "ix_workflow_node_runs_status_claim_expires_at", table_name="workflow_node_runs"
    )
    op.drop_column("workflow_node_runs", "execution_key")
    op.drop_column("workflow_node_runs", "last_heartbeat_at")
    op.drop_column("workflow_node_runs", "next_attempt_at")
    op.drop_column("workflow_node_runs", "worker_task_id")
    op.drop_column("workflow_node_runs", "claimed_at")
    op.drop_column("workflow_node_runs", "claim_expires_at")
    op.drop_column("workflow_node_runs", "claim_token")
