"""Account-scoped analytics dimensions and publish attribution (T4.4).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-15 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "published_posts",
        sa.Column(
            "account_display_snapshot",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.create_index(
        "ix_published_posts_tenant_id_social_account_id",
        "published_posts",
        ["tenant_id", "social_account_id"],
        unique=False,
    )

    op.add_column("analytics_snapshots", sa.Column("social_account_id", sa.Uuid(), nullable=True))
    op.add_column(
        "analytics_snapshots",
        sa.Column("account_label", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_analytics_snapshots_tenant_id_social_account_id",
        "analytics_snapshots",
        ["tenant_id", "social_account_id"],
        unique=False,
    )

    # Backfill snapshot attribution from live social accounts where possible.
    op.execute(
        """
        UPDATE published_posts p
        SET account_display_snapshot = json_build_object(
            'social_account_id', s.id::text,
            'platform', s.platform,
            'display_name', COALESCE(s.display_name, ''),
            'handle', COALESCE(s.handle, ''),
            'account_external_id', COALESCE(s.account_external_id, ''),
            'status', COALESCE(s.status, ''),
            'auth_type', COALESCE(s.auth_type, '')
        )::json
        FROM social_accounts s
        WHERE p.social_account_id = s.id
          AND (p.account_display_snapshot IS NULL OR p.account_display_snapshot::text = '{}')
        """
    )

    op.execute(
        """
        UPDATE analytics_snapshots a
        SET social_account_id = p.social_account_id,
            account_label = CASE
              WHEN p.account_display_snapshot->>'handle' IS NOT NULL
                   AND btrim(p.account_display_snapshot->>'handle') <> ''
                THEN (p.platform || ' · ' || (p.account_display_snapshot->>'handle'))
              WHEN p.account_display_snapshot->>'display_name' IS NOT NULL
                   AND btrim(p.account_display_snapshot->>'display_name') <> ''
                THEN (p.platform || ' · ' || (p.account_display_snapshot->>'display_name'))
              WHEN p.social_account_id IS NOT NULL
                THEN (p.platform || ' · ' || left(p.social_account_id::text, 8))
              ELSE p.platform
            END
        FROM published_posts p
        WHERE a.published_post_id = p.id
          AND a.social_account_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analytics_snapshots_tenant_id_social_account_id",
        table_name="analytics_snapshots",
    )
    op.drop_column("analytics_snapshots", "account_label")
    op.drop_column("analytics_snapshots", "social_account_id")
    op.drop_index(
        "ix_published_posts_tenant_id_social_account_id",
        table_name="published_posts",
    )
    op.drop_column("published_posts", "account_display_snapshot")
