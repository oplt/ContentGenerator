"""Add chess_content_opportunity_scores (Phase 17).

Revision ID: f0a1b2c3d4e6
Revises: f9a0b1c2d3e4
Create Date: 2026-09-16 17:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e6"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_content_opportunity_scores",
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
        sa.Column("analysis_job_id", sa.Uuid(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("formula_version", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["chess_analysis_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chess_content_opp_tenant_game",
        "chess_content_opportunity_scores",
        ["tenant_id", "chess_game_id"],
    )
    op.create_index(
        "ix_chess_content_opp_analysis_job_id",
        "chess_content_opportunity_scores",
        ["analysis_job_id"],
    )
    op.create_index(
        "ix_chess_content_opp_tenant_score",
        "chess_content_opportunity_scores",
        ["tenant_id", "score"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_content_opp_tenant_score", table_name="chess_content_opportunity_scores")
    op.drop_index("ix_chess_content_opp_analysis_job_id", table_name="chess_content_opportunity_scores")
    op.drop_index("ix_chess_content_opp_tenant_game", table_name="chess_content_opportunity_scores")
    op.drop_table("chess_content_opportunity_scores")
