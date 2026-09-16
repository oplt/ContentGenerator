"""Chess schema hardening: soft-delete-aware fingerprint uniqueness (Phase 23).

Revision ID: f2a3b4c5d6e8
Revises: f1a2b3c4d5e7
Create Date: 2026-09-16 15:15:00.000000

Existing deployments keep all prior chess tables/FKs/indexes from e3f4…f1a2.
This revision only adjusts fingerprint uniqueness so soft-deleted rows do not
block re-import (mirrors provider/external partial uniques).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e8"
down_revision: Union[str, None] = "f1a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_chess_games_tenant_id_game_fingerprint",
        "chess_games",
        type_="unique",
    )
    op.create_index(
        "uq_chess_games_tenant_id_game_fingerprint",
        "chess_games",
        ["tenant_id", "game_fingerprint"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_constraint(
        "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
        "chess_puzzles",
        type_="unique",
    )
    op.create_index(
        "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
        "chess_puzzles",
        ["tenant_id", "puzzle_fingerprint"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
        table_name="chess_puzzles",
    )
    op.create_unique_constraint(
        "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
        "chess_puzzles",
        ["tenant_id", "puzzle_fingerprint"],
    )

    op.drop_index(
        "uq_chess_games_tenant_id_game_fingerprint",
        table_name="chess_games",
    )
    op.create_unique_constraint(
        "uq_chess_games_tenant_id_game_fingerprint",
        "chess_games",
        ["tenant_id", "game_fingerprint"],
    )
