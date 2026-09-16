"""Add chess_tactical_patterns table (Phase 16).

Revision ID: f9a0b1c2d3e4
Revises: f8a9b0c1d2e4
Create Date: 2026-09-16 16:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, None] = "f8a9b0c1d2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_tactical_patterns",
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
        sa.Column("pattern", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detection_method", sa.String(length=64), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["chess_analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chess_tactical_patterns_job_id", "chess_tactical_patterns", ["analysis_job_id"])
    op.create_index(
        "ix_chess_tactical_patterns_chess_game_id",
        "chess_tactical_patterns",
        ["chess_game_id"],
    )
    op.create_index(
        "ix_chess_tactical_patterns_tenant_game",
        "chess_tactical_patterns",
        ["tenant_id", "chess_game_id"],
    )
    op.create_index(
        "ix_chess_tactical_patterns_job_ply_pattern",
        "chess_tactical_patterns",
        ["analysis_job_id", "ply", "pattern"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_tactical_patterns_job_ply_pattern", table_name="chess_tactical_patterns")
    op.drop_index("ix_chess_tactical_patterns_tenant_game", table_name="chess_tactical_patterns")
    op.drop_index("ix_chess_tactical_patterns_chess_game_id", table_name="chess_tactical_patterns")
    op.drop_index("ix_chess_tactical_patterns_job_id", table_name="chess_tactical_patterns")
    op.drop_table("chess_tactical_patterns")
