"""Alembic: puzzle provenance columns + video→catalog game FK.

Revision ID: f1a2b3c4d5e7
Revises: f0a1b2c3d4e6
Create Date: 2026-09-16 14:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, None] = "f0a1b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chess_puzzles",
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "chess_puzzles",
        sa.Column("import_batch_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "chess_puzzles",
        sa.Column("license_note", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_chess_puzzles_tenant_id_import_batch",
        "chess_puzzles",
        ["tenant_id", "import_batch_id"],
    )

    op.add_column(
        "chess_video_jobs",
        sa.Column("chess_game_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_chess_video_jobs_chess_game_id",
        "chess_video_jobs",
        "chess_games",
        ["chess_game_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_chess_video_jobs_chess_game_id",
        "chess_video_jobs",
        ["chess_game_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_video_jobs_chess_game_id", table_name="chess_video_jobs")
    op.drop_constraint(
        "fk_chess_video_jobs_chess_game_id", "chess_video_jobs", type_="foreignkey"
    )
    op.drop_column("chess_video_jobs", "chess_game_id")

    op.drop_index("ix_chess_puzzles_tenant_id_import_batch", table_name="chess_puzzles")
    op.drop_column("chess_puzzles", "license_note")
    op.drop_column("chess_puzzles", "import_batch_id")
    op.drop_column("chess_puzzles", "retrieved_at")
