"""Workflow definition versioning: draft save + immutable publish."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.compiler import WorkflowCompileResult, WorkflowCompiler
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.models import (
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    WorkflowVersion,
)
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.security import sanitize_mapping, sanitize_workflow_graph


class WorkflowVersioningService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        compiler: WorkflowCompiler | None = None,
    ) -> None:
        self.db = db
        self.repo = WorkflowRepository(db)
        self.compiler = compiler or WorkflowCompiler()

    async def create_definition(
        self,
        *,
        tenant_id: UUID,
        name: str,
        slug: str,
        description: str | None,
        created_by_user_id: UUID | None,
    ) -> WorkflowDefinition:
        existing = await self.repo.get_definition_by_slug(tenant_id, slug)
        if existing is not None:
            raise HTTPException(status_code=409, detail=f"slug '{slug}' already exists")
        definition = WorkflowDefinition(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            status=WorkflowDefinitionStatus.DRAFT.value,
            created_by_user_id=created_by_user_id,
        )
        return await self.repo.add_definition(definition)

    async def save_draft(
        self,
        *,
        tenant_id: UUID,
        definition_id: UUID,
        graph: WorkflowGraph | dict[str, Any],
        created_by_user_id: UUID | None,
        input_schema_json: dict[str, Any] | None = None,
        output_schema_json: dict[str, Any] | None = None,
    ) -> WorkflowVersion:
        definition = await self._require_definition(tenant_id, definition_id)
        parsed = sanitize_workflow_graph(graph)
        latest = await self.repo.latest_version(tenant_id, definition_id)

        if latest is not None and latest.published_at is None:
            self.repo.assert_mutable(latest)
            latest.graph_json = parsed.model_dump(mode="json")
            latest.input_schema_json = sanitize_mapping(
                input_schema_json or latest.input_schema_json
            )
            latest.output_schema_json = sanitize_mapping(
                output_schema_json or latest.output_schema_json
            )
            latest.checksum = None
            await self.db.flush()
            return latest

        version_number = await self.repo.next_version_number(tenant_id, definition_id)
        draft = WorkflowVersion(
            tenant_id=tenant_id,
            workflow_definition_id=definition.id,
            version=version_number,
            graph_json=parsed.model_dump(mode="json"),
            input_schema_json=sanitize_mapping(input_schema_json),
            output_schema_json=sanitize_mapping(output_schema_json),
            created_by_user_id=created_by_user_id,
        )
        return await self.repo.add_version(draft)

    async def publish(
        self,
        *,
        tenant_id: UUID,
        definition_id: UUID,
        version_id: UUID | None = None,
        context: CompileContext | None = None,
    ) -> WorkflowVersion:
        definition = await self._require_definition(tenant_id, definition_id)
        if version_id is not None:
            version = await self.repo.get_version(tenant_id, version_id)
            if version is None or version.workflow_definition_id != definition.id:
                raise HTTPException(status_code=404, detail="Workflow version not found")
        else:
            version = await self.repo.latest_version(tenant_id, definition_id)
            if version is None:
                raise HTTPException(status_code=400, detail="No draft version to publish")

        if version.published_at is not None:
            raise HTTPException(status_code=409, detail="Version already published")

        result = self.compiler.validate_graph(version.graph_json, context)
        if not result.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Workflow graph failed validation",
                    "errors": [e.model_dump() for e in result.errors],
                },
            )

        assert result.checksum is not None
        if result.normalized_graph is not None:
            graph = sanitize_workflow_graph(result.normalized_graph)
            # New publishes use the port/binding resolver; do not mutate already-published rows.
            if int(graph.schema_version or 1) < 2:
                graph = graph.model_copy(update={"schema_version": 2})
            version.graph_json = graph.model_dump(mode="json")
        self.repo.mark_published(version, checksum=result.checksum)
        definition.current_version_id = version.id
        definition.status = WorkflowDefinitionStatus.ACTIVE.value
        await self.db.flush()
        return version

    def validate_graph(
        self,
        graph: dict[str, Any] | WorkflowGraph,
        context: CompileContext | None = None,
    ) -> WorkflowCompileResult:
        return self.compiler.validate_graph(graph, context)

    async def _require_definition(
        self, tenant_id: UUID, definition_id: UUID
    ) -> WorkflowDefinition:
        definition = await self.repo.get_definition(tenant_id, definition_id)
        if definition is None:
            raise HTTPException(status_code=404, detail="Workflow definition not found")
        return definition
