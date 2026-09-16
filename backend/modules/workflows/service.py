"""Workflow facade: node registry + definition versioning."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.compiler import WorkflowCompileResult, WorkflowCompiler
from backend.modules.workflows.graph_schema import CompileContext, RuntimeClientContext, WorkflowGraph
from backend.modules.workflows.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workflows.nodes.base import WorkflowNodeNotFoundError
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun
from backend.modules.workflows.run_repository import WorkflowRunRepository
from backend.modules.workflows.schemas import (
    NodeConfigValidateResponse,
    NodeDefinitionResponse,
    NodeTestResponse,
)
from backend.modules.workflows.versioning import WorkflowVersioningService


class WorkflowService:
    def __init__(
        self,
        db: AsyncSession | None = None,
        registry: WorkflowNodeRegistry | None = None,
    ) -> None:
        self.registry = registry or get_default_registry()
        self.compiler = WorkflowCompiler(self.registry)
        self.db = db
        self.repo = WorkflowRepository(db) if db is not None else None
        self.run_repo = WorkflowRunRepository(db) if db is not None else None
        self._versioning = (
            WorkflowVersioningService(db, compiler=self.compiler) if db is not None else None
        )

    def list_nodes(self) -> list[NodeDefinitionResponse]:
        return self.registry.list_definitions()

    def get_node(self, node_type: str, version: int | None = None) -> NodeDefinitionResponse:
        node = self.registry.get(node_type, version)
        return self.registry.to_definition(node)

    def validate_node_config(
        self,
        node_type: str,
        config: dict[str, Any],
        version: int | None = None,
    ) -> NodeConfigValidateResponse:
        try:
            node = self.registry.get(node_type, version)
        except WorkflowNodeNotFoundError as exc:
            return NodeConfigValidateResponse(
                valid=False,
                node_type=node_type,
                version=version or 0,
                errors=[str(exc)],
            )
        try:
            normalized = node.validate_config(config)
        except ValidationError as exc:
            return NodeConfigValidateResponse(
                valid=False,
                node_type=node.type,
                version=node.version,
                errors=[e["msg"] for e in exc.errors()],
            )
        return NodeConfigValidateResponse(
            valid=True,
            node_type=node.type,
            version=node.version,
            normalized_config=normalized.model_dump(mode="json"),
        )

    def validate_graph(
        self,
        graph: dict[str, Any] | WorkflowGraph,
        context: CompileContext | dict[str, Any] | None = None,
    ) -> WorkflowCompileResult:
        return self.compiler.validate_graph(graph, context)

    async def create_definition(
        self,
        *,
        tenant_id: UUID,
        name: str,
        slug: str,
        description: str | None,
        created_by_user_id: UUID | None,
    ) -> WorkflowDefinition:
        definition = await self._versioning_required().create_definition(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            created_by_user_id=created_by_user_id,
        )
        from backend.modules.workflows.audit_hooks import record_workflow_audit

        await record_workflow_audit(
            self._db_required(),
            tenant_id=tenant_id,
            actor_user_id=created_by_user_id,
            action="workflows.definition_created",
            entity_type="workflow_definition",
            entity_id=str(definition.id),
            message="Workflow definition created",
            payload={"slug": definition.slug},
        )
        return definition

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
        return await self._versioning_required().save_draft(
            tenant_id=tenant_id,
            definition_id=definition_id,
            graph=graph,
            created_by_user_id=created_by_user_id,
            input_schema_json=input_schema_json,
            output_schema_json=output_schema_json,
        )

    async def publish_version(
        self,
        *,
        tenant_id: UUID,
        definition_id: UUID,
        version_id: UUID | None = None,
        context: CompileContext | None = None,
        actor_user_id: UUID | None = None,
    ) -> WorkflowVersion:
        version = await self._versioning_required().publish(
            tenant_id=tenant_id,
            definition_id=definition_id,
            version_id=version_id,
            context=context,
        )
        from backend.modules.workflows.audit_hooks import record_workflow_audit

        await record_workflow_audit(
            self._db_required(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="workflows.version_published",
            entity_type="workflow_version",
            entity_id=str(version.id),
            message="Workflow version published",
            payload={
                "workflow_definition_id": str(definition_id),
                "version": version.version,
            },
        )
        return version

    async def list_definitions(self, tenant_id: UUID) -> list[WorkflowDefinition]:
        return await self._repo_required().list_definitions(tenant_id)

    async def get_definition(
        self, tenant_id: UUID, definition_id: UUID
    ) -> WorkflowDefinition | None:
        return await self._repo_required().get_definition(tenant_id, definition_id)

    async def list_versions(
        self, tenant_id: UUID, definition_id: UUID
    ) -> list[WorkflowVersion]:
        return await self._repo_required().list_versions(tenant_id, definition_id)

    async def list_runs(
        self, tenant_id: UUID, *, limit: int = 50, status: str | None = None
    ) -> list[WorkflowRun]:
        return await self._run_repo_required().list_runs(
            tenant_id, limit=limit, status=status
        )

    async def get_run(self, tenant_id: UUID, run_id: UUID) -> WorkflowRun | None:
        return await self._run_repo_required().get_run(tenant_id, run_id)

    async def list_node_runs(
        self, tenant_id: UUID, workflow_run_id: UUID
    ) -> list[WorkflowNodeRun]:
        return await self._run_repo_required().list_node_runs(tenant_id, workflow_run_id)

    async def start_run(
        self,
        *,
        tenant_id: UUID,
        workflow_version_id: UUID,
        trigger_payload: dict[str, Any] | None = None,
        initial_inputs: dict[str, Any] | None = None,
        automation_id: UUID | None = None,
        brand_id: UUID | None = None,
        correlation_id: str | None = None,
        compile_context: CompileContext | RuntimeClientContext | None = None,
        trigger_type: str = "manual",
        run_config: dict[str, Any] | None = None,
        advance: bool = True,
        dry_run: bool = False,
        mock_generation: bool = False,
        simulate_approval: bool = False,
        actor_user_id: UUID | None = None,
    ) -> WorkflowRun:
        from backend.modules.workflows import service_runtime

        return await service_runtime.start_run_with_audit(
            self,
            tenant_id=tenant_id,
            workflow_version_id=workflow_version_id,
            trigger_payload=trigger_payload,
            initial_inputs=initial_inputs,
            automation_id=automation_id,
            brand_id=brand_id,
            correlation_id=correlation_id,
            compile_context=compile_context,
            trigger_type=trigger_type,
            run_config=run_config,
            advance=advance,
            dry_run=dry_run,
            mock_generation=mock_generation,
            simulate_approval=simulate_approval,
            actor_user_id=actor_user_id,
        )

    async def test_node(self, **kwargs: Any) -> NodeTestResponse:
        from backend.modules.workflows import service_runtime

        return await service_runtime.test_node(self, **kwargs)

    async def advance_run(self, tenant_id: UUID, run_id: UUID) -> WorkflowRun:
        from backend.modules.workflows import service_runtime

        return await service_runtime.advance_run(self, tenant_id, run_id)

    async def resume_run(self, tenant_id: UUID, **kwargs: Any) -> WorkflowRun:
        from backend.modules.workflows import service_runtime

        return await service_runtime.resume_run(self, tenant_id, **kwargs)

    def _db_required(self) -> AsyncSession:
        if self.db is None:
            raise RuntimeError("WorkflowService requires a DB session")
        return self.db

    def _versioning_required(self) -> WorkflowVersioningService:
        if self._versioning is None:
            raise RuntimeError("WorkflowService requires a DB session for versioning")
        return self._versioning

    def _repo_required(self) -> WorkflowRepository:
        if self.repo is None:
            raise RuntimeError("WorkflowService requires a DB session for persistence")
        return self.repo

    def _run_repo_required(self) -> WorkflowRunRepository:
        if self.run_repo is None:
            raise RuntimeError("WorkflowService requires a DB session for run state")
        return self.run_repo
