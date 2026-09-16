"""Add chess_games and chess_puzzles canonical catalog tables.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-16 13:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_games",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("white_player", sa.String(length=255), nullable=True),
        sa.Column("black_player", sa.String(length=255), nullable=True),
        sa.Column("white_rating", sa.Integer(), nullable=True),
        sa.Column("black_rating", sa.Integer(), nullable=True),
        sa.Column("event", sa.String(length=255), nullable=True),
        sa.Column("site", sa.String(length=255), nullable=True),
        sa.Column("round", sa.String(length=64), nullable=True),
        sa.Column("game_date", sa.String(length=64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("eco", sa.String(length=16), nullable=True),
        sa.Column("opening", sa.String(length=255), nullable=True),
        sa.Column("variation", sa.String(length=255), nullable=True),
        sa.Column("starting_fen", sa.String(length=128), nullable=False),
        sa.Column("final_fen", sa.String(length=128), nullable=True),
        sa.Column("normalized_pgn", sa.Text(), nullable=False),
        sa.Column("move_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_provider", sa.String(length=64), nullable=True),
        sa.Column("source_external_id", sa.String(length=128), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("game_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_famous", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("famous_title", sa.String(length=255), nullable=True),
        sa.Column("historical_tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chess_games"),
        sa.UniqueConstraint(
            "tenant_id",
            "game_fingerprint",
            name="uq_chess_games_tenant_id_game_fingerprint",
        ),
    )
    op.create_index("ix_chess_games_tenant_id", "chess_games", ["tenant_id"], unique=False)
    op.create_index("ix_chess_games_tenant_id_year", "chess_games", ["tenant_id", "year"], unique=False)
    op.create_index("ix_chess_games_tenant_id_eco", "chess_games", ["tenant_id", "eco"], unique=False)
    op.create_index(
        "ix_chess_games_tenant_id_is_famous",
        "chess_games",
        ["tenant_id", "is_famous"],
        unique=False,
    )
    op.create_index(
        "ix_chess_games_tenant_id_content_hash",
        "chess_games",
        ["tenant_id", "content_hash"],
        unique=False,
    )
    op.create_index(
        "uq_chess_games_tenant_provider_external",
        "chess_games",
        ["tenant_id", "source_provider", "source_external_id"],
        unique=True,
        postgresql_where=sa.text("source_external_id IS NOT NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "chess_puzzles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("starting_fen", sa.String(length=128), nullable=False),
        sa.Column("solution_moves_uci", sa.JSON(), nullable=False),
        sa.Column("solution_moves_san", sa.JSON(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("rating_deviation", sa.Float(), nullable=True),
        sa.Column("popularity", sa.Integer(), nullable=True),
        sa.Column("play_count", sa.Integer(), nullable=True),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("opening_tags", sa.JSON(), nullable=False),
        sa.Column("source_game_id", sa.String(length=128), nullable=True),
        sa.Column("source_game_url", sa.String(length=1024), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("puzzle_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chess_puzzles"),
        sa.UniqueConstraint(
            "tenant_id",
            "puzzle_fingerprint",
            name="uq_chess_puzzles_tenant_id_puzzle_fingerprint",
        ),
    )
    op.create_index("ix_chess_puzzles_tenant_id", "chess_puzzles", ["tenant_id"], unique=False)
    op.create_index(
        "ix_chess_puzzles_tenant_id_rating",
        "chess_puzzles",
        ["tenant_id", "rating"],
        unique=False,
    )
    op.create_index(
        "uq_chess_puzzles_tenant_provider_external",
        "chess_puzzles",
        ["tenant_id", "provider", "external_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_chess_puzzles_tenant_provider_external", table_name="chess_puzzles")
    op.drop_index("ix_chess_puzzles_tenant_id_rating", table_name="chess_puzzles")
    op.drop_index("ix_chess_puzzles_tenant_id", table_name="chess_puzzles")
    op.drop_table("chess_puzzles")

    op.drop_index("uq_chess_games_tenant_provider_external", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_content_hash", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_is_famous", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_eco", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id_year", table_name="chess_games")
    op.drop_index("ix_chess_games_tenant_id", table_name="chess_games")
    op.drop_table("chess_games")
