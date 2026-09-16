"""Phase 20 — hot-path indexes for workflow/publish/approval/ops retention.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-16 11:05:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # READY node claim: run-scoped scan ordered by created_at
    op.create_index(
        "ix_workflow_node_runs_ready_run_created_at",
        "workflow_node_runs",
        ["workflow_run_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'ready'"),
        sqlite_where=sa.text("status = 'ready'"),
    )
    # Expired claim recovery
    op.create_index(
        "ix_workflow_node_runs_expired_claims",
        "workflow_node_runs",
        ["claim_expires_at"],
        unique=False,
        postgresql_where=sa.text(
            "status IN ('running', 'queued') AND claim_expires_at IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status IN ('running', 'queued') AND claim_expires_at IS NOT NULL"
        ),
    )
    # Finished nodes for payload retention
    op.create_index(
        "ix_workflow_node_runs_finished_at_terminal",
        "workflow_node_runs",
        ["finished_at"],
        unique=False,
        postgresql_where=sa.text(
            "finished_at IS NOT NULL AND status IN "
            "('succeeded', 'failed', 'cancelled', 'skipped')"
        ),
        sqlite_where=sa.text(
            "finished_at IS NOT NULL AND status IN "
            "('succeeded', 'failed', 'cancelled', 'skipped')"
        ),
    )
    # Due waits
    op.create_index(
        "ix_workflow_waits_pending_wake_at",
        "workflow_waits",
        ["wake_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending' AND wake_at IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND wake_at IS NOT NULL"),
    )
    # Runs by tenant/status/date
    op.create_index(
        "ix_workflow_runs_tenant_status_created_at",
        "workflow_runs",
        ["tenant_id", "status", sa.text("created_at DESC")],
        unique=False,
    )
    # Publishing jobs by account + approval linkage
    op.create_index(
        "ix_publishing_jobs_tenant_social_account_created_at",
        "publishing_jobs",
        ["tenant_id", "social_account_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_publishing_jobs_approval_request_id",
        "publishing_jobs",
        ["approval_request_id"],
        unique=False,
        postgresql_where=sa.text("approval_request_id IS NOT NULL"),
        sqlite_where=sa.text("approval_request_id IS NOT NULL"),
    )
    # Approvals awaiting response (status + expires)
    op.create_index(
        "ix_approval_requests_pending_expires_at",
        "approval_requests",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    # Retention scans
    op.create_index(
        "ix_task_executions_created_at",
        "task_executions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhooks_inbox_status_received_at",
        "webhooks_inbox",
        ["status", "received_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_webhooks_inbox_status_received_at", table_name="webhooks_inbox")
    op.drop_index("ix_task_executions_created_at", table_name="task_executions")
    op.drop_index(
        "ix_approval_requests_pending_expires_at", table_name="approval_requests"
    )
    op.drop_index(
        "ix_publishing_jobs_approval_request_id", table_name="publishing_jobs"
    )
    op.drop_index(
        "ix_publishing_jobs_tenant_social_account_created_at",
        table_name="publishing_jobs",
    )
    op.drop_index(
        "ix_workflow_runs_tenant_status_created_at", table_name="workflow_runs"
    )
    op.drop_index("ix_workflow_waits_pending_wake_at", table_name="workflow_waits")
    op.drop_index(
        "ix_workflow_node_runs_finished_at_terminal", table_name="workflow_node_runs"
    )
    op.drop_index(
        "ix_workflow_node_runs_expired_claims", table_name="workflow_node_runs"
    )
    op.drop_index(
        "ix_workflow_node_runs_ready_run_created_at", table_name="workflow_node_runs"
    )
