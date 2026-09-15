"""add source next_poll_at and due index

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-15 15:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))

    # Backfill: never-polled sources are due now; otherwise schedule from last poll + interval.
    op.execute(
        """
        UPDATE sources
        SET next_poll_at = CASE
            WHEN last_polled_at IS NULL THEN NOW()
            ELSE last_polled_at + (polling_interval_minutes || ' minutes')::interval
        END
        WHERE deleted_at IS NULL
        """
    )

    op.create_index(
        "ix_sources_due_next_poll_at",
        "sources",
        ["next_poll_at"],
        unique=False,
        postgresql_where=sa.text("active IS true AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sources_due_next_poll_at",
        table_name="sources",
        postgresql_where=sa.text("active IS true AND deleted_at IS NULL"),
    )
    op.drop_column("sources", "next_poll_at")
