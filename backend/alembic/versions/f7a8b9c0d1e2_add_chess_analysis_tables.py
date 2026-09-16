"""Add chess Stockfish analysis job + position tables (Phase 14).

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d1
Create Date: 2026-09-16 15:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e5f6a7b8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_analysis_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("chess_game_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=True),
        sa.Column("time_limit_seconds", sa.Float(), nullable=True),
        sa.Column("hash_mb", sa.Integer(), nullable=False),
        sa.Column("threads", sa.Integer(), nullable=False),
        sa.Column("engine_name", sa.String(length=128), nullable=True),
        sa.Column("engine_version", sa.String(length=128), nullable=True),
        sa.Column("analysis_settings", sa.JSON(), nullable=False),
        sa.Column("ply_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chess_analysis_jobs_tenant_id", "chess_analysis_jobs", ["tenant_id"])
    op.create_index("ix_chess_analysis_jobs_chess_game_id", "chess_analysis_jobs", ["chess_game_id"])
    op.create_index(
        "ix_chess_analysis_jobs_tenant_id_status",
        "chess_analysis_jobs",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_chess_analysis_jobs_tenant_game_created",
        "chess_analysis_jobs",
        ["tenant_id", "chess_game_id", "created_at"],
    )

    op.create_table(
        "chess_position_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("chess_game_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_job_id", sa.Uuid(), nullable=False),
        sa.Column("ply", sa.Integer(), nullable=False),
        sa.Column("fen", sa.String(length=128), nullable=False),
        sa.Column("evaluation_cp", sa.Integer(), nullable=True),
        sa.Column("mate_in", sa.Integer(), nullable=True),
        sa.Column("evaluation_before_cp", sa.Integer(), nullable=True),
        sa.Column("mate_before", sa.Integer(), nullable=True),
        sa.Column("evaluation_after_cp", sa.Integer(), nullable=True),
        sa.Column("mate_after", sa.Integer(), nullable=True),
        sa.Column("evaluation_delta", sa.Integer(), nullable=True),
        sa.Column("best_move_uci", sa.String(length=16), nullable=True),
        sa.Column("best_move_san", sa.String(length=32), nullable=True),
        sa.Column("played_move_uci", sa.String(length=16), nullable=False),
        sa.Column("played_move_san", sa.String(length=32), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("nodes", sa.Integer(), nullable=False),
        sa.Column("engine_name", sa.String(length=128), nullable=True),
        sa.Column("engine_version", sa.String(length=128), nullable=True),
        sa.Column("analysis_settings", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_job_id"], ["chess_analysis_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_job_id", "ply", name="uq_chess_position_analyses_job_ply"),
    )
    op.create_index("ix_chess_position_analyses_job_id", "chess_position_analyses", ["analysis_job_id"])
    op.create_index(
        "ix_chess_position_analyses_chess_game_id",
        "chess_position_analyses",
        ["chess_game_id"],
    )
    op.create_index(
        "ix_chess_position_analyses_tenant_game",
        "chess_position_analyses",
        ["tenant_id", "chess_game_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_position_analyses_tenant_game", table_name="chess_position_analyses")
    op.drop_index("ix_chess_position_analyses_chess_game_id", table_name="chess_position_analyses")
    op.drop_index("ix_chess_position_analyses_job_id", table_name="chess_position_analyses")
    op.drop_table("chess_position_analyses")
    op.drop_index("ix_chess_analysis_jobs_tenant_game_created", table_name="chess_analysis_jobs")
    op.drop_index("ix_chess_analysis_jobs_tenant_id_status", table_name="chess_analysis_jobs")
    op.drop_index("ix_chess_analysis_jobs_chess_game_id", table_name="chess_analysis_jobs")
    op.drop_index("ix_chess_analysis_jobs_tenant_id", table_name="chess_analysis_jobs")
    op.drop_table("chess_analysis_jobs")
