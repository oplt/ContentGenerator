"""Add chess_critical_moments table (Phase 15).

Revision ID: f8a9b0c1d2e4
Revises: f7a8b9c0d1e2
Create Date: 2026-09-16 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e4"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_critical_moments",
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
        sa.Column("chess_game_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_job_id", sa.Uuid(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detection_method", sa.String(length=64), nullable=False),
        sa.Column("engine_facts", sa.JSON(), nullable=False),
        sa.Column("heuristic_summary", sa.Text(), nullable=False),
        sa.Column("editorial_description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["chess_analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chess_critical_moments_job_id", "chess_critical_moments", ["analysis_job_id"])
    op.create_index(
        "ix_chess_critical_moments_chess_game_id",
        "chess_critical_moments",
        ["chess_game_id"],
    )
    op.create_index(
        "ix_chess_critical_moments_tenant_game",
        "chess_critical_moments",
        ["tenant_id", "chess_game_id"],
    )
    op.create_index(
        "ix_chess_critical_moments_job_ply_class",
        "chess_critical_moments",
        ["analysis_job_id", "ply", "classification"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_critical_moments_job_ply_class", table_name="chess_critical_moments")
    op.drop_index("ix_chess_critical_moments_tenant_game", table_name="chess_critical_moments")
    op.drop_index("ix_chess_critical_moments_chess_game_id", table_name="chess_critical_moments")
    op.drop_index("ix_chess_critical_moments_job_id", table_name="chess_critical_moments")
    op.drop_table("chess_critical_moments")
