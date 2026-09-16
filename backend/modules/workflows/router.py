"""Workflow registry + definition HTTP routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.workflows.compiler import WorkflowCompileResult
from backend.modules.workflows.nodes.base import WorkflowNodeNotFoundError
from backend.modules.workflows.schemas import (
    GraphSimulateRequest,
    GraphValidateRequest,
    NodeConfigValidateRequest,
    NodeConfigValidateResponse,
    NodeDefinitionResponse,
    NodeTestRequest,
    NodeTestResponse,
    WorkflowDefinitionCreateRequest,
    WorkflowDefinitionResponse,
    WorkflowDraftSaveRequest,
    WorkflowPublishRequest,
    WorkflowVersionResponse,
)
from backend.modules.workflows.service import WorkflowService

router = APIRouter()


@router.get("/nodes", response_model=list[NodeDefinitionResponse])
async def list_workflow_nodes(
    membership: TenantUser = Depends(get_current_membership),
) -> list[NodeDefinitionResponse]:
    _ = membership
    return WorkflowService().list_nodes()


@router.get("/nodes/{node_type}", response_model=NodeDefinitionResponse)
async def get_workflow_node(
    node_type: str,
    version: int | None = Query(default=None),
    membership: TenantUser = Depends(get_current_membership),
) -> NodeDefinitionResponse:
    _ = membership
    try:
        return WorkflowService().get_node(node_type, version)
    except WorkflowNodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/nodes/{node_type}/validate-config", response_model=NodeConfigValidateResponse)
async def validate_workflow_node_config(
    node_type: str,
    payload: NodeConfigValidateRequest,
    membership: TenantUser = Depends(get_current_membership),
) -> NodeConfigValidateResponse:
    _ = membership
    return WorkflowService().validate_node_config(node_type, payload.config, payload.version)


@router.post("/nodes/{node_type}/test", response_model=NodeTestResponse)
async def test_workflow_node(
    node_type: str,
    payload: NodeTestRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> NodeTestResponse:
    """Execute one node with supplied inputs (tenant-scoped; publish forced dry-run)."""
    return await WorkflowService(db).test_node(
        tenant_id=membership.tenant_id,
        node_type=node_type,
        config=payload.config,
        inputs=payload.inputs,
        version=payload.version,
        dry_run=payload.dry_run,
        mock_generation=payload.mock_generation,
        brand_id=payload.brand_id,
        compile_context=payload.context,
    )


@router.post("/validate-graph", response_model=WorkflowCompileResult)
async def validate_workflow_graph(
    payload: GraphValidateRequest,
    membership: TenantUser = Depends(get_current_membership),
) -> WorkflowCompileResult:
    """Design-time validation. Hypothetical capability maps are allowed."""
    _ = membership
    return WorkflowService().validate_graph(payload.graph, payload.context)


@router.post("/simulate-graph", response_model=WorkflowCompileResult)
async def simulate_workflow_graph(
    payload: GraphSimulateRequest,
    membership: TenantUser = Depends(get_current_membership),
) -> WorkflowCompileResult:
    """Explicit design-time capability simulation (hypothetical caps OK).

    Runtime execution never trusts client-supplied capability maps — use this
    endpoint (or ``/validate-graph``) only for editor what-if checks.
    """
    _ = membership
    return WorkflowService().validate_graph(payload.graph, payload.context)


@router.get("/definitions", response_model=list[WorkflowDefinitionResponse])
async def list_workflow_definitions(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowDefinitionResponse]:
    rows = await WorkflowService(db).list_definitions(membership.tenant_id)
    return [WorkflowDefinitionResponse.model_validate(row) for row in rows]


@router.post("/definitions", response_model=WorkflowDefinitionResponse, status_code=201)
async def create_workflow_definition(
    payload: WorkflowDefinitionCreateRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    row = await WorkflowService(db).create_definition(
        tenant_id=membership.tenant_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        created_by_user_id=membership.user_id,
    )
    return WorkflowDefinitionResponse.model_validate(row)


@router.get("/definitions/{definition_id}", response_model=WorkflowDefinitionResponse)
async def get_workflow_definition(
    definition_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    row = await WorkflowService(db).get_definition(membership.tenant_id, definition_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    return WorkflowDefinitionResponse.model_validate(row)


@router.get(
    "/definitions/{definition_id}/versions",
    response_model=list[WorkflowVersionResponse],
)
async def list_workflow_versions(
    definition_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowVersionResponse]:
    service = WorkflowService(db)
    definition = await service.get_definition(membership.tenant_id, definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    rows = await service.list_versions(membership.tenant_id, definition_id)
    return [WorkflowVersionResponse.model_validate(row) for row in rows]


@router.put(
    "/definitions/{definition_id}/draft",
    response_model=WorkflowVersionResponse,
)
async def save_workflow_draft(
    definition_id: UUID,
    payload: WorkflowDraftSaveRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowVersionResponse:
    row = await WorkflowService(db).save_draft(
        tenant_id=membership.tenant_id,
        definition_id=definition_id,
        graph=payload.graph,
        created_by_user_id=membership.user_id,
        input_schema_json=payload.input_schema_json,
        output_schema_json=payload.output_schema_json,
    )
    return WorkflowVersionResponse.model_validate(row)


@router.post(
    "/definitions/{definition_id}/publish",
    response_model=WorkflowVersionResponse,
)
async def publish_workflow_version(
    definition_id: UUID,
    payload: WorkflowPublishRequest | None = None,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowVersionResponse:
    body = payload or WorkflowPublishRequest()
    row = await WorkflowService(db).publish_version(
        tenant_id=membership.tenant_id,
        definition_id=definition_id,
        version_id=body.version_id,
        context=body.context,
        actor_user_id=membership.user_id,
    )
    return WorkflowVersionResponse.model_validate(row)
