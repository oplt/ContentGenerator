"""Add chess_games indexes for player / event / game_date search (§35).

Revision ID: h6b7c8d9e0f1
Revises: g5a6b7c8d9e0
Create Date: 2026-09-16 17:50:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "h6b7c8d9e0f1"
down_revision: Union[str, None] = "g5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_chess_games_tenant_id_white_player",
        "chess_games",
        ["tenant_id", "white_player"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_black_player",
        "chess_games",
        ["tenant_id", "black_player"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_event",
        "chess_games",
        ["tenant_id", "event"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_game_date",
        "chess_games",
        ["tenant_id", "game_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chess_games_tenant_id_game_date", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_event", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_black_player", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_white_player", table_name="chess_games")
