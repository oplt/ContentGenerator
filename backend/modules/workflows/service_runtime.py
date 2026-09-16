"""WorkflowService run/test helpers (kept separate for line budget)."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from uuid import UUID

from backend.modules.workflows.engine import WorkflowEngine
from backend.modules.workflows.graph_schema import CompileContext, RuntimeClientContext
from backend.modules.workflows.run_models import WorkflowRun
from backend.modules.workflows.schemas import NodeTestResponse

if TYPE_CHECKING:
    from backend.modules.workflows.service import WorkflowService


async def start_run_with_audit(
    service: WorkflowService,
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
    from backend.modules.workflows.audit_hooks import record_workflow_audit

    run = await WorkflowEngine(service._db_required(), registry=service.registry).start_run(
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
    )
    await record_workflow_audit(
        service._db_required(),
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action="workflows.run_started",
        entity_type="workflow_run",
        entity_id=str(run.id),
        message="Workflow run started",
        payload={
            "trigger_type": run.trigger_type,
            "dry_run": dry_run,
            "workflow_version_id": str(workflow_version_id),
        },
        correlation_id=correlation_id or run.correlation_id,
    )
    return run


async def advance_run(service: WorkflowService, tenant_id: UUID, run_id: UUID) -> WorkflowRun:
    return await WorkflowEngine(service._db_required(), registry=service.registry).advance(
        tenant_id, run_id
    )


async def resume_run(
    service: WorkflowService,
    tenant_id: UUID,
    *,
    resume_token: str | None = None,
    event_key: str | None = None,
    outcome: str,
    decision: dict[str, Any] | None = None,
    advance: bool = True,
) -> WorkflowRun:
    from fastapi import HTTPException

    from backend.modules.workflows.engine_resume import resume_waiting_node
    from backend.modules.workflows.wait_store import resolve_wait_by_event_key

    db = service._db_required()
    token = resume_token
    decision_payload = dict(decision or {})
    if token is None and event_key:
        wait = await resolve_wait_by_event_key(
            db,
            tenant_id=tenant_id,
            event_key=event_key,
            payload=decision_payload,
        )
        if wait is None:
            raise HTTPException(status_code=404, detail="Pending wait not found for event_key")
        token = wait.resume_token
        outcome = "received"
        if isinstance(decision_payload.get("event_payload"), dict):
            decision_payload = {
                **decision_payload,
                "event_payload": decision_payload["event_payload"],
            }
        elif decision_payload:
            decision_payload = {"event_payload": decision_payload}

    if not token:
        raise HTTPException(status_code=422, detail="resume_token or event_key is required")

    engine = WorkflowEngine(db, registry=service.registry)
    return await resume_waiting_node(
        engine,
        tenant_id,
        resume_token=token,
        outcome=outcome,
        decision=decision_payload,
        advance=advance,
    )


async def test_node(
    service: WorkflowService,
    *,
    tenant_id: UUID,
    node_type: str,
    config: dict[str, Any] | None = None,
    inputs: dict[str, Any] | None = None,
    version: int | None = None,
    dry_run: bool = True,
    mock_generation: bool = False,
    brand_id: UUID | None = None,
    compile_context: CompileContext | RuntimeClientContext | None = None,
) -> NodeTestResponse:
    from backend.modules.workflows.node_tester import WorkflowNodeTester

    return await WorkflowNodeTester(service._db_required(), registry=service.registry).test_node(
        tenant_id=tenant_id,
        node_type=node_type,
        config=config,
        inputs=inputs,
        version=version,
        dry_run=dry_run,
        mock_generation=mock_generation,
        brand_id=brand_id,
        compile_context=compile_context,
    )
