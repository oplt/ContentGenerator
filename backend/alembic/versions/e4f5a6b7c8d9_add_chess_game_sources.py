"""Add chess_game_sources for multi-provider provenance on one canonical game.

Revision ID: e4f5a6b7c8d9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-16 13:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chess_game_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("chess_game_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("import_batch_id", sa.String(length=64), nullable=True),
        sa.Column("license_note", sa.String(length=512), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chess_game_id"], ["chess_games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_chess_game_sources"),
    )
    op.create_index("ix_chess_game_sources_tenant_id", "chess_game_sources", ["tenant_id"])
    op.create_index(
        "ix_chess_game_sources_chess_game_id",
        "chess_game_sources",
        ["chess_game_id"],
    )
    op.create_index(
        "uq_chess_game_sources_tenant_provider_external",
        "chess_game_sources",
        ["tenant_id", "provider", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "ix_chess_game_sources_game_provider_batch",
        "chess_game_sources",
        ["chess_game_id", "provider", "import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chess_game_sources_game_provider_batch", table_name="chess_game_sources")
    op.drop_index("uq_chess_game_sources_tenant_provider_external", table_name="chess_game_sources")
    op.drop_index("ix_chess_game_sources_chess_game_id", table_name="chess_game_sources")
    op.drop_index("ix_chess_game_sources_tenant_id", table_name="chess_game_sources")
    op.drop_table("chess_game_sources")
