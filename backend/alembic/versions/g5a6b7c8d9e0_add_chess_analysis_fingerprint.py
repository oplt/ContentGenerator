"""Alembic: analysis_fingerprint on chess_analysis_jobs (versioned reuse §12/§13).

Revision ID: g5a6b7c8d9e0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-16 16:50:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g5a6b7c8d9e0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chess_analysis_jobs",
        sa.Column("analysis_fingerprint", sa.String(length=64), nullable=True),
    )
    # Legacy rows: unique placeholder so NOT NULL + unique index can apply.
    op.execute(
        sa.text(
            "UPDATE chess_analysis_jobs "
            "SET analysis_fingerprint = 'legacy:' || replace(id::text, '-', '') "
            "WHERE analysis_fingerprint IS NULL"
        )
    )
    op.alter_column(
        "chess_analysis_jobs",
        "analysis_fingerprint",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_index(
        "ix_chess_analysis_jobs_tenant_fingerprint",
        "chess_analysis_jobs",
        ["tenant_id", "analysis_fingerprint"],
    )
    op.create_index(
        "uq_chess_analysis_jobs_tenant_fingerprint_active",
        "chess_analysis_jobs",
        ["tenant_id", "analysis_fingerprint"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'completed')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_chess_analysis_jobs_tenant_fingerprint_active",
        table_name="chess_analysis_jobs",
    )
    op.drop_index(
        "ix_chess_analysis_jobs_tenant_fingerprint",
        table_name="chess_analysis_jobs",
    )
    op.drop_column("chess_analysis_jobs", "analysis_fingerprint")
