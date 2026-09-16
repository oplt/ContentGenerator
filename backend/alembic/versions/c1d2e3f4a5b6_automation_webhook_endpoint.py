"""Add automations.webhook_endpoint_id for Phase 17 ingress lookup.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-09-16 10:40:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automations",
        sa.Column("webhook_endpoint_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_automations_webhook_endpoint_id",
        "automations",
        ["webhook_endpoint_id"],
        unique=True,
        postgresql_where=sa.text("webhook_endpoint_id IS NOT NULL"),
        sqlite_where=sa.text("webhook_endpoint_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_automations_webhook_endpoint_id", table_name="automations")
    op.drop_column("automations", "webhook_endpoint_id")
