"""Add board_theme to chess_video_jobs.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-15 23:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chess_video_jobs",
        sa.Column(
            "board_theme",
            sa.String(length=32),
            nullable=False,
            server_default="classic_wood",
        ),
    )


def downgrade() -> None:
    op.drop_column("chess_video_jobs", "board_theme")
