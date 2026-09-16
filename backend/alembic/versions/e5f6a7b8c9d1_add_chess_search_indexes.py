"""Add chess catalog search indexes for Phase 10 API.

Revision ID: e5f6a7b8c9d1
Revises: e4f5a6b7c8d9
Create Date: 2026-09-16 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d1"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_chess_games_tenant_id_created_at",
        "chess_games",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_result",
        "chess_games",
        ["tenant_id", "result"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_provider",
        "chess_games",
        ["tenant_id", "source_provider"],
        unique=False,
    )
    op.create_index(
        "ix_chess_puzzles_tenant_id_popularity",
        "chess_puzzles",
        ["tenant_id", "popularity"],
        unique=False,
    )
    op.create_index(
        "ix_chess_puzzles_tenant_id_provider",
        "chess_puzzles",
        ["tenant_id", "provider"],
        unique=False,
    )
    op.create_index(
        "ix_chess_puzzles_tenant_id_created_at",
        "chess_puzzles",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chess_puzzles_tenant_id_created_at", table_name="chess_puzzles")
    op.drop_index("ix_chess_puzzles_tenant_id_provider", table_name="chess_puzzles")
    op.drop_index("ix_chess_puzzles_tenant_id_popularity", table_name="chess_puzzles")
    op.drop_index("ix_chess_games_tenant_id_provider", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_result", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_created_at", table_name="chess_games")
