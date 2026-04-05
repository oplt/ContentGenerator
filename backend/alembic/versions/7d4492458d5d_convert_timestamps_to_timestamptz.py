"""convert timestamps to timestamptz

Revision ID: 7d4492458d5d
Revises: 422dc4bc95ff
Create Date: 2026-04-02 19:28:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7d4492458d5d"
down_revision: Union[str, Sequence[str], None] = "422dc4bc95ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TIMESTAMP_COLUMNS = (
    ("users", "created_at"),
    ("audit_logs", "created_at"),
    ("notifications", "created_at"),
    ("projects", "created_at"),
    ("refresh_sessions", "created_at"),
    ("refresh_sessions", "expires_at"),
    ("user_profiles", "updated_at"),
)


def upgrade() -> None:
    """Upgrade schema."""
    for table_name, column_name in TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table_name, column_name in TIMESTAMP_COLUMNS:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
        )
