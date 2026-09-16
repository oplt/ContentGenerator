"""Workflow definition / version persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.models import WorkflowDefinition, WorkflowVersion


class WorkflowRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_definition(
        self, tenant_id: UUID, definition_id: UUID
    ) -> WorkflowDefinition | None:
        result = await self.db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.id == definition_id,
                WorkflowDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_definition_by_slug(
        self, tenant_id: UUID, slug: str
    ) -> WorkflowDefinition | None:
        result = await self.db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.slug == slug,
                WorkflowDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_definitions(self, tenant_id: UUID) -> list[WorkflowDefinition]:
        result = await self.db.execute(
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.deleted_at.is_(None),
            )
            .order_by(WorkflowDefinition.updated_at.desc())
        )
        return list(result.scalars().all())

    async def add_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        self.db.add(definition)
        await self.db.flush()
        return definition

    async def get_version(
        self, tenant_id: UUID, version_id: UUID
    ) -> WorkflowVersion | None:
        result = await self.db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.id == version_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self, tenant_id: UUID, definition_id: UUID
    ) -> list[WorkflowVersion]:
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_definition_id == definition_id,
            )
            .order_by(WorkflowVersion.version.desc())
        )
        return list(result.scalars().all())

    async def latest_version(
        self, tenant_id: UUID, definition_id: UUID
    ) -> WorkflowVersion | None:
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_definition_id == definition_id,
            )
            .order_by(WorkflowVersion.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_version_number(self, tenant_id: UUID, definition_id: UUID) -> int:
        result = await self.db.execute(
            select(func.max(WorkflowVersion.version)).where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.workflow_definition_id == definition_id,
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def add_version(self, version: WorkflowVersion) -> WorkflowVersion:
        self.db.add(version)
        await self.db.flush()
        return version

    @staticmethod
    def assert_mutable(version: WorkflowVersion) -> None:
        if version.published_at is not None:
            raise PermissionError(
                f"WorkflowVersion {version.id} is published and immutable"
            )

    @staticmethod
    def mark_published(version: WorkflowVersion, *, checksum: str) -> WorkflowVersion:
        version.published_at = datetime.now(timezone.utc)
        version.checksum = checksum
        return version
