"""add trending_repos table

Revision ID: a1b2c3d4e5f6
Revises: 75927330b2a9
Create Date: 2026-04-09 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "75927330b2a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trending_repos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("github_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("full_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("html_url", sa.String(512), nullable=False),
        sa.Column("language", sa.String(64), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("stars_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watchers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_gained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("product_ideas", sa.JSON(), nullable=True),
        sa.Column("ideas_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trending_repos")),
    )
    op.create_index("ix_trending_repos_tenant_id", "trending_repos", ["tenant_id"])
    op.create_index(
        "ix_trending_repos_tenant_period_date",
        "trending_repos",
        ["tenant_id", "period", "snapshot_date"],
    )
    op.create_index(
        "ix_trending_repos_tenant_date",
        "trending_repos",
        ["tenant_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_trending_repos_tenant_date", table_name="trending_repos")
    op.drop_index("ix_trending_repos_tenant_period_date", table_name="trending_repos")
    op.drop_index("ix_trending_repos_tenant_id", table_name="trending_repos")
    op.drop_table("trending_repos")
