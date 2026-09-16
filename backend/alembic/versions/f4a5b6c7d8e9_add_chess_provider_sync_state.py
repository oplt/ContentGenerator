"""Alembic: chess_provider_sync_states (durable feed checkpoints; ≠ catalog jobs).

Revision ID: f4a5b6c7d8e9
Revises: f3a4b5c6d7e9
Create Date: 2026-09-16 16:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "f3a4b5c6d7e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_provider_sync_states",
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("sync_key", sa.String(length=128), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("cursor", sa.String(length=512), nullable=True),
        sa.Column("high_water_mark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lookback_seconds", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", sa.Uuid(), nullable=True),
        sa.Column("state_metadata", sa.JSON(), nullable=False),
        sa.Column("last_error_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "sync_key",
            name="uq_chess_provider_sync_tenant_provider_key",
        ),
    )
    op.create_index(
        "ix_chess_provider_sync_tenant_id",
        "chess_provider_sync_states",
        ["tenant_id"],
    )
    op.create_index(
        "ix_chess_provider_sync_tenant_provider",
        "chess_provider_sync_states",
        ["tenant_id", "provider"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chess_provider_sync_tenant_provider",
        table_name="chess_provider_sync_states",
    )
    op.drop_index(
        "ix_chess_provider_sync_tenant_id",
        table_name="chess_provider_sync_states",
    )
    op.drop_table("chess_provider_sync_states")
