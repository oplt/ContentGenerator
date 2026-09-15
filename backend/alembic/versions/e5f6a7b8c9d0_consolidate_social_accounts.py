"""Consolidate social accounts: lineage fields, active token binding, targets.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-15 15:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- SocialAccount canonical fields ---
    op.add_column(
        "social_accounts",
        sa.Column("auth_type", sa.String(length=64), nullable=False, server_default="oauth"),
    )
    op.add_column(
        "social_accounts",
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "social_accounts",
        sa.Column("legacy_connected_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "social_accounts",
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_social_accounts_tenant_id_platform_status",
        "social_accounts",
        ["tenant_id", "platform", "status"],
        unique=False,
    )
    op.create_index(
        "ix_social_accounts_legacy_connected_account_id",
        "social_accounts",
        ["legacy_connected_account_id"],
        unique=False,
    )

    # --- Active credential binding ---
    op.add_column(
        "social_account_tokens",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "social_account_tokens",
        sa.Column("binding_version", sa.Integer(), nullable=False, server_default="1"),
    )

    # Deactivate older duplicates: keep latest non-deleted as active.
    op.execute(
        """
        UPDATE social_account_tokens t
        SET is_active = false
        WHERE t.deleted_at IS NULL
          AND t.id NOT IN (
            SELECT DISTINCT ON (social_account_id) id
            FROM social_account_tokens
            WHERE deleted_at IS NULL
            ORDER BY social_account_id, created_at DESC
          )
        """
    )

    op.create_index(
        "uq_social_account_tokens_active_binding",
        "social_account_tokens",
        ["social_account_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS true AND deleted_at IS NULL"),
    )

    # --- Content target account lists (additive; empty = platform-only compat) ---
    op.add_column(
        "content_plans",
        sa.Column(
            "target_social_account_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "content_jobs",
        sa.Column(
            "target_social_account_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "generated_asset_groups",
        sa.Column(
            "target_social_account_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )

    # --- Backfill: mint external ids for social rows missing provider identity ---
    op.execute(
        """
        UPDATE social_accounts
        SET account_external_id = 'legacy:social:' || id::text
        WHERE deleted_at IS NULL
          AND (account_external_id IS NULL OR btrim(account_external_id) = '')
        """
    )

    # --- Backfill: create social from orphan connected; link existing ---
    op.execute(
        """
        INSERT INTO social_accounts (
            id, tenant_id, platform, display_name, handle, account_external_id,
            status, auth_type, capability_flags, settings, metadata,
            legacy_connected_account_id, created_at, updated_at, version
        )
        SELECT
            gen_random_uuid(),
            c.tenant_id,
            c.platform,
            c.account_name,
            NULL,
            'legacy:connected:' || c.id::text,
            CASE
                WHEN c.status = 'quarantined' THEN 'quarantined'
                WHEN c.status = 'needs_reauth' THEN 'needs_reauth'
                WHEN c.status = 'disconnected' THEN 'disconnected'
                ELSE 'connected'
            END,
            COALESCE(NULLIF(c.auth_type, ''), 'oauth'),
            '{}'::json,
            '{}'::json,
            COALESCE(c.metadata, '{}'::json),
            c.id,
            NOW(),
            NOW(),
            1
        FROM connected_accounts c
        WHERE c.deleted_at IS NULL
          AND c.social_account_id IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM social_accounts s
            WHERE s.tenant_id = c.tenant_id
              AND s.platform = c.platform
              AND s.account_external_id = 'legacy:connected:' || c.id::text
              AND s.deleted_at IS NULL
          )
        """
    )

    op.execute(
        """
        UPDATE connected_accounts c
        SET social_account_id = s.id
        FROM social_accounts s
        WHERE c.deleted_at IS NULL
          AND c.social_account_id IS NULL
          AND s.deleted_at IS NULL
          AND s.legacy_connected_account_id = c.id
        """
    )

    op.execute(
        """
        UPDATE connected_accounts c
        SET social_account_id = s.id
        FROM social_accounts s
        WHERE c.deleted_at IS NULL
          AND c.social_account_id IS NULL
          AND s.deleted_at IS NULL
          AND s.tenant_id = c.tenant_id
          AND s.platform = c.platform
          AND s.account_external_id = 'legacy:connected:' || c.id::text
        """
    )

    # Stamp lineage on already-linked social rows.
    op.execute(
        """
        UPDATE social_accounts s
        SET legacy_connected_account_id = c.id
        FROM connected_accounts c
        WHERE c.social_account_id = s.id
          AND c.deleted_at IS NULL
          AND s.legacy_connected_account_id IS NULL
        """
    )

    # Quarantine duplicate connected names (keep earliest linked).
    op.execute(
        """
        UPDATE connected_accounts c
        SET status = 'quarantined',
            metadata = (COALESCE(c.metadata::jsonb, '{}'::jsonb) || '{"quarantine_reason":"duplicate_platform_account_name"}'::jsonb)::json
        WHERE c.deleted_at IS NULL
          AND c.id IN (
            SELECT id FROM (
              SELECT id,
                     ROW_NUMBER() OVER (
                       PARTITION BY tenant_id, platform, lower(account_name)
                       ORDER BY (social_account_id IS NULL), created_at ASC, id ASC
                     ) AS rn
              FROM connected_accounts
              WHERE deleted_at IS NULL
            ) ranked
            WHERE rn > 1
          )
        """
    )

    # Publishing jobs: inherit social_account_id from connected projection.
    op.execute(
        """
        UPDATE publishing_jobs j
        SET social_account_id = c.social_account_id
        FROM connected_accounts c
        WHERE j.social_account_id IS NULL
          AND j.connected_account_id = c.id
          AND c.social_account_id IS NOT NULL
        """
    )

    # Soft unique: one live connected projection per social account.
    op.create_index(
        "uq_connected_accounts_social_account_id_live",
        "connected_accounts",
        ["social_account_id"],
        unique=True,
        postgresql_where=sa.text(
            "social_account_id IS NOT NULL AND deleted_at IS NULL AND status <> 'quarantined'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_connected_accounts_social_account_id_live",
        table_name="connected_accounts",
        postgresql_where=sa.text(
            "social_account_id IS NOT NULL AND deleted_at IS NULL AND status <> 'quarantined'"
        ),
    )
    op.drop_column("generated_asset_groups", "target_social_account_ids")
    op.drop_column("content_jobs", "target_social_account_ids")
    op.drop_column("content_plans", "target_social_account_ids")
    op.drop_index(
        "uq_social_account_tokens_active_binding",
        table_name="social_account_tokens",
        postgresql_where=sa.text("is_active IS true AND deleted_at IS NULL"),
    )
    op.drop_column("social_account_tokens", "binding_version")
    op.drop_column("social_account_tokens", "is_active")
    op.drop_index("ix_social_accounts_legacy_connected_account_id", table_name="social_accounts")
    op.drop_index("ix_social_accounts_tenant_id_platform_status", table_name="social_accounts")
    op.drop_column("social_accounts", "quarantine_reason")
    op.drop_column("social_accounts", "legacy_connected_account_id")
    op.drop_column("social_accounts", "settings")
    op.drop_column("social_accounts", "auth_type")
