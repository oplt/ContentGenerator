"""Workflow run inspection + operator recovery HTTP routes (Phase 15)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.workflow_cancellation import cancel_run
from backend.modules.workflows.operator_recovery import (
    resume_node,
    retry_from_node,
    retry_node,
)
from backend.modules.workflows.run_inspection import build_run_detail
from backend.modules.workflows.schemas import (
    WorkflowResumeNodeRequest,
    WorkflowResumeRequest,
    WorkflowRunDetailResponse,
    WorkflowRunResponse,
    WorkflowStartRunRequest,
)
from backend.modules.workflows.service import WorkflowService

router = APIRouter()


async def _detail(
    db: AsyncSession, service: WorkflowService, tenant_id: UUID, run_id: UUID
) -> WorkflowRunDetailResponse:
    run = await service.get_run(tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    nodes = await service.list_node_runs(tenant_id, run_id)
    return await build_run_detail(db, run=run, nodes=nodes)


@router.get("/runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowRunResponse]:
    rows = await WorkflowService(db).list_runs(
        membership.tenant_id, limit=limit, status=status
    )
    return [WorkflowRunResponse.model_validate(row) for row in rows]


@router.get("/runs/{run_id}", response_model=WorkflowRunDetailResponse)
async def get_workflow_run(
    run_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    return await _detail(db, WorkflowService(db), membership.tenant_id, run_id)


@router.post(
    "/definitions/{definition_id}/runs",
    response_model=WorkflowRunDetailResponse,
    status_code=201,
)
async def start_workflow_run(
    definition_id: UUID,
    payload: WorkflowStartRunRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    service = WorkflowService(db)
    definition = await service.get_definition(membership.tenant_id, definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Workflow definition not found")
    version_id = payload.workflow_version_id or definition.current_version_id
    if version_id is None:
        raise HTTPException(status_code=400, detail="No published workflow version")
    run = await service.start_run(
        tenant_id=membership.tenant_id,
        workflow_version_id=version_id,
        trigger_payload=payload.trigger_payload,
        initial_inputs=payload.initial_inputs,
        automation_id=payload.automation_id,
        brand_id=payload.brand_id,
        correlation_id=payload.correlation_id,
        compile_context=payload.context,
        advance=payload.advance,
        run_config=payload.run_config,
        dry_run=payload.dry_run,
        mock_generation=payload.mock_generation,
        simulate_approval=payload.simulate_approval,
        actor_user_id=membership.user_id,
    )
    nodes = await service.list_node_runs(membership.tenant_id, run.id)
    return await build_run_detail(db, run=run, nodes=nodes)


@router.post("/runs/{run_id}/advance", response_model=WorkflowRunDetailResponse)
async def advance_workflow_run(
    run_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    service = WorkflowService(db)
    run = await service.advance_run(membership.tenant_id, run_id)
    return await _detail(db, service, membership.tenant_id, run.id)


@router.post("/resume", response_model=WorkflowRunDetailResponse)
async def resume_workflow_waiting_node(
    payload: WorkflowResumeRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    """Resume a WAITING node via resume_token or durable event_key."""
    service = WorkflowService(db)
    run = await service.resume_run(
        membership.tenant_id,
        resume_token=payload.resume_token,
        event_key=payload.event_key,
        outcome=payload.outcome,
        decision=payload.decision,
        advance=payload.advance,
    )
    return await _detail(db, service, membership.tenant_id, run.id)


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunDetailResponse)
async def cancel_workflow_run(
    run_id: UUID,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    engine = WorkflowEngine(db)
    run = await cancel_run(engine, membership.tenant_id, run_id)
    return await _detail(db, WorkflowService(db), membership.tenant_id, run.id)


@router.post(
    "/runs/{run_id}/nodes/{node_id}/retry",
    response_model=WorkflowRunDetailResponse,
)
async def retry_workflow_node(
    run_id: UUID,
    node_id: str,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    engine = WorkflowEngine(db)
    run = await retry_node(engine, membership.tenant_id, run_id, node_id)
    return await _detail(db, WorkflowService(db), membership.tenant_id, run.id)


@router.post(
    "/runs/{run_id}/retry-from/{node_id}",
    response_model=WorkflowRunDetailResponse,
)
async def retry_workflow_from_node(
    run_id: UUID,
    node_id: str,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    engine = WorkflowEngine(db)
    run = await retry_from_node(engine, membership.tenant_id, run_id, node_id)
    return await _detail(db, WorkflowService(db), membership.tenant_id, run.id)


@router.post(
    "/runs/{run_id}/nodes/{node_id}/resume",
    response_model=WorkflowRunDetailResponse,
)
async def resume_workflow_node(
    run_id: UUID,
    node_id: str,
    payload: WorkflowResumeNodeRequest,
    membership: TenantUser = Depends(require_permission("content:write")),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunDetailResponse:
    engine = WorkflowEngine(db)
    run = await resume_node(
        engine,
        membership.tenant_id,
        run_id,
        node_id,
        outcome=payload.outcome,
        decision=payload.decision,
        advance=payload.advance,
    )
    return await _detail(db, WorkflowService(db), membership.tenant_id, run.id)
