"""Workflow domain foundation: brand↔account links + reusable automations.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-16 00:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite unique keys so child FKs can pin tenant_id with parent identity.
    op.create_unique_constraint("uq_brands_tenant_id_id", "brands", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_social_accounts_tenant_id_id", "social_accounts", ["tenant_id", "id"]
    )

    op.create_table(
        "brand_social_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("default_content_format", sa.String(length=32), nullable=True),
        sa.Column("generation_overrides", sa.JSON(), nullable=False),
        sa.Column("publishing_policy", sa.JSON(), nullable=False),
        sa.Column("platform_policy", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_brand_social_accounts_tenant_brand",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "social_account_id"],
            ["social_accounts.tenant_id", "social_accounts.id"],
            name="fk_brand_social_accounts_tenant_social_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_brand_social_accounts"),
        sa.UniqueConstraint(
            "tenant_id",
            "brand_id",
            "social_account_id",
            name="uq_brand_social_accounts_tenant_brand_account",
        ),
    )
    op.create_index(
        "ix_brand_social_accounts_tenant_id_brand_id",
        "brand_social_accounts",
        ["tenant_id", "brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_brand_social_accounts_tenant_id_social_account_id",
        "brand_social_accounts",
        ["tenant_id", "social_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_brand_social_accounts_tenant_id_enabled",
        "brand_social_accounts",
        ["tenant_id", "enabled"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_definitions"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_workflow_definitions_tenant_id_slug"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workflow_definitions_tenant_id_id"),
    )
    op.create_index(
        "ix_workflow_definitions_tenant_id_status",
        "workflow_definitions",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_definitions_tenant_id_enabled",
        "workflow_definitions",
        ["tenant_id", "deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph_json", sa.JSON(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_workflow_versions_tenant_definition",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_versions"),
        sa.UniqueConstraint(
            "tenant_id",
            "workflow_definition_id",
            "version",
            name="uq_workflow_versions_tenant_definition_version",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workflow_versions_tenant_id_id"),
    )
    op.create_index(
        "ix_workflow_versions_tenant_id_definition_id",
        "workflow_versions",
        ["tenant_id", "workflow_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_versions_tenant_id_published_at",
        "workflow_versions",
        ["tenant_id", "published_at"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "automations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_definition_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version_id", sa.Uuid(), nullable=False),
        sa.Column("brand_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("trigger_type", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("trigger_config", sa.JSON(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_definition_id"],
            ["workflow_definitions.tenant_id", "workflow_definitions.id"],
            name="fk_automations_tenant_workflow_definition",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_version_id"],
            ["workflow_versions.tenant_id", "workflow_versions.id"],
            name="fk_automations_tenant_workflow_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brand_id"],
            ["brands.tenant_id", "brands.id"],
            name="fk_automations_tenant_brand",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automations"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_automations_tenant_id_id"),
    )
    op.create_index(
        "ix_automations_tenant_id_enabled",
        "automations",
        ["tenant_id", "enabled"],
        unique=False,
    )
    op.create_index(
        "ix_automations_tenant_id_brand_id",
        "automations",
        ["tenant_id", "brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_automations_tenant_id_workflow_definition_id",
        "automations",
        ["tenant_id", "workflow_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_automations_tenant_id_next_run_at",
        "automations",
        ["tenant_id", "next_run_at"],
        unique=False,
    )
    op.create_index(
        "ix_automations_enabled_next_run_at",
        "automations",
        ["enabled", "next_run_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "automation_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("overrides_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "automation_id"],
            ["automations.tenant_id", "automations.id"],
            name="fk_automation_targets_tenant_automation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "social_account_id"],
            ["social_accounts.tenant_id", "social_accounts.id"],
            name="fk_automation_targets_tenant_social_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_automation_targets"),
        sa.UniqueConstraint(
            "tenant_id",
            "automation_id",
            "social_account_id",
            name="uq_automation_targets_tenant_automation_account",
        ),
    )
    op.create_index(
        "ix_automation_targets_tenant_id_automation_id",
        "automation_targets",
        ["tenant_id", "automation_id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_targets_tenant_id_social_account_id",
        "automation_targets",
        ["tenant_id", "social_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_automation_targets_tenant_id_enabled",
        "automation_targets",
        ["tenant_id", "enabled"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_automation_targets_tenant_id_enabled", table_name="automation_targets")
    op.drop_index(
        "ix_automation_targets_tenant_id_social_account_id", table_name="automation_targets"
    )
    op.drop_index("ix_automation_targets_tenant_id_automation_id", table_name="automation_targets")
    op.drop_table("automation_targets")

    op.drop_index("ix_automations_enabled_next_run_at", table_name="automations")
    op.drop_index("ix_automations_tenant_id_next_run_at", table_name="automations")
    op.drop_index("ix_automations_tenant_id_workflow_definition_id", table_name="automations")
    op.drop_index("ix_automations_tenant_id_brand_id", table_name="automations")
    op.drop_index("ix_automations_tenant_id_enabled", table_name="automations")
    op.drop_table("automations")

    op.drop_constraint(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        type_="foreignkey",
    )
    op.drop_index("ix_workflow_versions_tenant_id_published_at", table_name="workflow_versions")
    op.drop_index("ix_workflow_versions_tenant_id_definition_id", table_name="workflow_versions")
    op.drop_table("workflow_versions")

    op.drop_index("ix_workflow_definitions_tenant_id_enabled", table_name="workflow_definitions")
    op.drop_index("ix_workflow_definitions_tenant_id_status", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")

    op.drop_index("ix_brand_social_accounts_tenant_id_enabled", table_name="brand_social_accounts")
    op.drop_index(
        "ix_brand_social_accounts_tenant_id_social_account_id",
        table_name="brand_social_accounts",
    )
    op.drop_index("ix_brand_social_accounts_tenant_id_brand_id", table_name="brand_social_accounts")
    op.drop_table("brand_social_accounts")

    op.drop_constraint("uq_social_accounts_tenant_id_id", "social_accounts", type_="unique")
    op.drop_constraint("uq_brands_tenant_id_id", "brands", type_="unique")
