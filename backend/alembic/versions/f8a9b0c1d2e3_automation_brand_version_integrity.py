"""Harden automation brand/version integrity with composite FKs (Phase 6).

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-16 09:20:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_workflow_versions_tenant_definition_id",
        "workflow_versions",
        ["tenant_id", "workflow_definition_id", "id"],
    )

    # Automations: version must belong to the same definition.
    op.drop_constraint(
        "fk_automations_tenant_workflow_version",
        "automations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_automations_tenant_definition_version",
        "automations",
        "workflow_versions",
        ["tenant_id", "workflow_definition_id", "workflow_version_id"],
        ["tenant_id", "workflow_definition_id", "id"],
        ondelete="RESTRICT",
    )

    # Definitions: current_version must belong to this definition/tenant.
    op.drop_constraint(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workflow_definitions_current_version_composite",
        "workflow_definitions",
        "workflow_versions",
        ["tenant_id", "id", "current_version_id"],
        ["tenant_id", "workflow_definition_id", "id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workflow_definitions_current_version_composite",
        "workflow_definitions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workflow_definitions_current_version_id",
        "workflow_definitions",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_automations_tenant_definition_version",
        "automations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_automations_tenant_workflow_version",
        "automations",
        "workflow_versions",
        ["tenant_id", "workflow_version_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "uq_workflow_versions_tenant_definition_id",
        "workflow_versions",
        type_="unique",
    )
