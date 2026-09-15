"""Add chess_video_jobs table for tenant-scoped chess render jobs.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-15 21:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_video_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_format", sa.String(length=16), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("normalized_pgn", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("white_player", sa.String(length=255), nullable=True),
        sa.Column("black_player", sa.String(length=255), nullable=True),
        sa.Column("event", sa.String(length=255), nullable=True),
        sa.Column("game_date", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("starting_fen", sa.String(length=128), nullable=True),
        sa.Column("move_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orientation", sa.String(length=16), nullable=False),
        sa.Column("render_preset", sa.String(length=32), nullable=False),
        sa.Column("seconds_per_move", sa.Float(), nullable=False, server_default="1"),
        sa.Column("include_coordinates", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_move_text", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("renderer_version", sa.String(length=32), nullable=True),
        sa.Column("render_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("video_storage_key", sa.String(length=512), nullable=True),
        sa.Column("video_public_url", sa.String(length=1024), nullable=True),
        sa.Column("thumbnail_storage_key", sa.String(length=512), nullable=True),
        sa.Column("thumbnail_public_url", sa.String(length=1024), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chess_video_jobs"),
    )
    op.create_index("ix_chess_video_jobs_tenant_id", "chess_video_jobs", ["tenant_id"], unique=False)
    op.create_index("ix_chess_video_jobs_status", "chess_video_jobs", ["status"], unique=False)
    op.create_index("ix_chess_video_jobs_created_at", "chess_video_jobs", ["created_at"], unique=False)
    op.create_index(
        "ix_chess_video_jobs_render_fingerprint",
        "chess_video_jobs",
        ["render_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_chess_video_jobs_tenant_id_created_at",
        "chess_video_jobs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chess_video_jobs_tenant_id_status",
        "chess_video_jobs",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chess_video_jobs_tenant_id_status", table_name="chess_video_jobs")
    op.drop_index("ix_chess_video_jobs_tenant_id_created_at", table_name="chess_video_jobs")
    op.drop_index("ix_chess_video_jobs_render_fingerprint", table_name="chess_video_jobs")
    op.drop_index("ix_chess_video_jobs_created_at", table_name="chess_video_jobs")
    op.drop_index("ix_chess_video_jobs_status", table_name="chess_video_jobs")
    op.drop_index("ix_chess_video_jobs_tenant_id", table_name="chess_video_jobs")
    op.drop_table("chess_video_jobs")
