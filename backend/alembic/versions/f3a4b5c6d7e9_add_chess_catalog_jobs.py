"""Alembic: chess_catalog_jobs for async import/enrich/sync (Phase 24).

Revision ID: f3a4b5c6d7e9
Revises: f2a3b4c5d6e8
Create Date: 2026-09-16 15:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3a4b5c6d7e9"
down_revision: Union[str, None] = "f2a3b4c5d6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_catalog_jobs",
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
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("import_batch_id", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chess_catalog_jobs_tenant_id", "chess_catalog_jobs", ["tenant_id"])
    op.create_index(
        "ix_chess_catalog_jobs_tenant_id_status",
        "chess_catalog_jobs",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_chess_catalog_jobs_tenant_id_kind",
        "chess_catalog_jobs",
        ["tenant_id", "kind"],
    )
    op.create_index(
        "ix_chess_catalog_jobs_tenant_created",
        "chess_catalog_jobs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_catalog_jobs_tenant_created", table_name="chess_catalog_jobs")
    op.drop_index("ix_chess_catalog_jobs_tenant_id_kind", table_name="chess_catalog_jobs")
    op.drop_index("ix_chess_catalog_jobs_tenant_id_status", table_name="chess_catalog_jobs")
    op.drop_index("ix_chess_catalog_jobs_tenant_id", table_name="chess_catalog_jobs")
    op.drop_table("chess_catalog_jobs")
