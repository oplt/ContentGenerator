"""Alembic: content_variants + publishing_jobs.content_variant_id (Phase 10).

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-16 09:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Required for composite tenant/job FK (same pattern as Phase 6 integrity).
    op.create_unique_constraint(
        "uq_content_jobs_tenant_id_id",
        "content_jobs",
        ["tenant_id", "id"],
    )

    op.create_table(
        "content_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("content_job_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_run_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("media_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "content_job_id"],
            ["content_jobs.tenant_id", "content_jobs.id"],
            name="fk_content_variants_tenant_content_job",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_content_variants_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "content_job_id",
            "fingerprint",
            name="uq_content_variants_tenant_job_fingerprint",
        ),
    )
    op.create_index(
        "ix_content_variants_tenant_id_content_job_id",
        "content_variants",
        ["tenant_id", "content_job_id"],
    )
    op.create_index(
        "ix_content_variants_tenant_id_platform",
        "content_variants",
        ["tenant_id", "platform"],
    )
    op.create_index("ix_content_variants_workflow_run_id", "content_variants", ["workflow_run_id"])

    op.create_table(
        "content_variant_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["social_account_id"], ["social_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["content_variants.tenant_id", "content_variants.id"],
            name="fk_content_variant_targets_tenant_variant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "variant_id",
            "social_account_id",
            name="uq_content_variant_targets_variant_account",
        ),
    )
    op.create_index("ix_content_variant_targets_variant_id", "content_variant_targets", ["variant_id"])
    op.create_index(
        "ix_content_variant_targets_social_account_id",
        "content_variant_targets",
        ["social_account_id"],
    )

    op.add_column(
        "publishing_jobs",
        sa.Column("content_variant_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_publishing_jobs_content_variant_id",
        "publishing_jobs",
        "content_variants",
        ["content_variant_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_publishing_jobs_content_variant_id",
        "publishing_jobs",
        ["content_variant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_publishing_jobs_content_variant_id", table_name="publishing_jobs")
    op.drop_constraint("fk_publishing_jobs_content_variant_id", "publishing_jobs", type_="foreignkey")
    op.drop_column("publishing_jobs", "content_variant_id")
    op.drop_index("ix_content_variant_targets_social_account_id", table_name="content_variant_targets")
    op.drop_index("ix_content_variant_targets_variant_id", table_name="content_variant_targets")
    op.drop_table("content_variant_targets")
    op.drop_index("ix_content_variants_workflow_run_id", table_name="content_variants")
    op.drop_index("ix_content_variants_tenant_id_platform", table_name="content_variants")
    op.drop_index("ix_content_variants_tenant_id_content_job_id", table_name="content_variants")
    op.drop_table("content_variants")
    op.drop_constraint("uq_content_jobs_tenant_id_id", "content_jobs", type_="unique")
