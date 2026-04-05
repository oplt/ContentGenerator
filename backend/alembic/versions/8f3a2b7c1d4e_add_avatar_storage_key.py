"""add avatar storage key

Revision ID: 8f3a2b7c1d4e
Revises: b0f58e52734d
Create Date: 2026-04-02 23:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f3a2b7c1d4e"
down_revision: Union[str, Sequence[str], None] = "b0f58e52734d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("user_profiles", sa.Column("avatar_storage_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_profiles", "avatar_storage_key")
