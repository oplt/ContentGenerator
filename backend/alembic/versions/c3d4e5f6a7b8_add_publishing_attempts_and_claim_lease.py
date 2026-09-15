"""add publishing attempt boundary and claim lease

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-15 15:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "publishing_jobs",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "publishing_jobs",
        sa.Column("current_attempt_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_publishing_jobs_status_claim_expires_at",
        "publishing_jobs",
        ["status", "claim_expires_at"],
        unique=False,
    )

    op.create_table(
        "publishing_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("publishing_job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("attempt_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("error_class", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("external_post_url", sa.String(length=1024), nullable=True),
        sa.Column("provider_payload", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["publishing_job_id"],
            ["publishing_jobs.id"],
            name=op.f("fk_publishing_attempts_publishing_job_id_publishing_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_publishing_attempts")),
        sa.UniqueConstraint("attempt_key", name="uq_publishing_attempts_attempt_key"),
        sa.UniqueConstraint(
            "publishing_job_id",
            "attempt_number",
            name="uq_publishing_attempts_job_id_attempt_number",
        ),
    )
    op.create_index(
        "ix_publishing_attempts_publishing_job_id_status",
        "publishing_attempts",
        ["publishing_job_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_publishing_attempts_publishing_job_id_status",
        table_name="publishing_attempts",
    )
    op.drop_table("publishing_attempts")
    op.drop_index("ix_publishing_jobs_status_claim_expires_at", table_name="publishing_jobs")
    op.drop_column("publishing_jobs", "current_attempt_key")
    op.drop_column("publishing_jobs", "claim_expires_at")
