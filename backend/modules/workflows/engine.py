"""Workflow orchestration engine. Claims READY nodes; workers execute one node."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.workflows.capability_context import build_runtime_compile_context
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.config_resolver import ConfigResolver
from backend.modules.workflows.engine_dispatch import (
    drain_inline_claimed_nodes,
    enqueue_claimed_node,
)
from backend.modules.workflows.engine_node_index import NodeRunIndex
from backend.modules.workflows.engine_ready import (
    ready_node_ids,
    root_node_ids,
    run_has_failure,
    run_is_waiting,
)
from backend.modules.workflows.engine_status import finalize_run_status
from backend.modules.workflows.graph_schema import CompileContext, RuntimeClientContext, WorkflowGraph
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.run_repository import WorkflowRunRepository
from backend.modules.workflows.runtime_bindings import authorize_runtime_bindings
from backend.modules.workflows.testing_support import merge_dry_run_config, testing_flags


class WorkflowEngine:
    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: WorkflowNodeRegistry | None = None,
        compiler: WorkflowCompiler | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or get_default_registry()
        self.compiler = compiler or WorkflowCompiler(self.registry)
        self.versions = WorkflowRepository(db)
        self.runs = WorkflowRunRepository(db)
        self.config_resolver = ConfigResolver(db, registry=self.registry)

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
    ) -> WorkflowRun:
        version = await self.versions.get_version(tenant_id, workflow_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Workflow version not found")
        if version.published_at is None:
            raise HTTPException(status_code=400, detail="Workflow version is not published")

        if correlation_id:
            existing = await self.runs.get_run_by_correlation(tenant_id, correlation_id)
            if existing is not None:
                if advance and existing.status in {
                    WorkflowRunStatus.QUEUED.value,
                    WorkflowRunStatus.RUNNING.value,
                }:
                    return await self.advance(tenant_id, existing.id)
                return existing

        client_ids = list(compile_context.social_account_ids) if compile_context else []
        await authorize_runtime_bindings(
            self.db,
            tenant_id=tenant_id,
            automation_id=automation_id,
            brand_id=brand_id,
            social_account_ids=client_ids,
        )
        compile_context = await build_runtime_compile_context(
            self.db,
            tenant_id=tenant_id,
            client=compile_context,
        )
        result = self.compiler.validate_graph(version.graph_json, compile_context)
        if not result.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Cannot start invalid workflow",
                    "errors": [e.model_dump() for e in result.errors],
                },
            )
        assert result.normalized_graph is not None
        graph = WorkflowGraph.model_validate(result.normalized_graph)
        run_config = merge_dry_run_config(run_config, dry_run=dry_run)
        if dry_run and trigger_type == "manual":
            trigger_type = "dry_run"

        now = datetime.now(timezone.utc)
        snapshot = await self.config_resolver.build_snapshot(
            tenant_id=tenant_id,
            graph=graph,
            graph_checksum=result.checksum,
            brand_id=brand_id,
            automation_id=automation_id,
            compile_context=compile_context,
            trigger_payload=dict(trigger_payload or {}),
            initial_inputs=dict(initial_inputs or {}),
            run_config=run_config,
        )
        snapshot["testing"] = testing_flags(
            dry_run=dry_run,
            mock_generation=mock_generation,
            simulate_approval=simulate_approval,
        )
        run = WorkflowRun(
            tenant_id=tenant_id,
            automation_id=automation_id,
            workflow_definition_id=version.workflow_definition_id,
            workflow_version_id=version.id,
            brand_id=brand_id,
            trigger_type=trigger_type or "manual",
            trigger_payload=dict(trigger_payload or {}),
            status=WorkflowRunStatus.QUEUED.value,
            context_snapshot=snapshot,
            started_at=now,
            correlation_id=correlation_id,
        )
        await self.runs.add_run(run)

        roots = set(root_node_ids(graph))
        for node in graph.nodes:
            status = (
                WorkflowNodeRunStatus.READY.value
                if node.id in roots
                else WorkflowNodeRunStatus.PENDING.value
            )
            await self.runs.add_node_run(
                WorkflowNodeRun(
                    tenant_id=tenant_id,
                    workflow_run_id=run.id,
                    node_id=node.id,
                    node_type=node.type,
                    node_version=node.version,
                    status=status,
                    iteration_key="",
                )
            )

        run.status = WorkflowRunStatus.RUNNING.value
        await self.db.flush()
        from backend.modules.workflows.observability import log_workflow_run_started

        log_workflow_run_started(run)
        if advance:
            run = await self.advance(tenant_id, run.id)
            if simulate_approval:
                from backend.modules.workflows.engine_simulate import auto_simulate_approvals

                run = await auto_simulate_approvals(self, tenant_id, run.id)
            return run
        return run

    async def advance(self, tenant_id: UUID, run_id: UUID) -> WorkflowRun:
        """Claim READY nodes and enqueue one-node workers. Does not execute domain work."""
        run = await self.runs.get_run(tenant_id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        if run.status in {
            WorkflowRunStatus.SUCCEEDED.value,
            WorkflowRunStatus.FAILED.value,
            WorkflowRunStatus.CANCELLED.value,
        }:
            return run

        version = await self.versions.get_version(tenant_id, run.workflow_version_id)
        if version is None:
            raise HTTPException(status_code=404, detail="Workflow version not found")
        graph = WorkflowGraph.model_validate(version.graph_json)

        # Drain loop: claim → enqueue (or inline execute) until waiting/failed/idle.
        for _ in range(max(8, len(graph.nodes) * 4, 32)):
            node_runs = await self._node_map(tenant_id, run.id)
            if run_is_waiting(node_runs) or run_has_failure(node_runs):
                break

            # Claim every READY row (including fan-out iterations), not one per node_id.
            claimable = [
                row
                for row in node_runs.rows
                if row.status == WorkflowNodeRunStatus.READY.value
            ]
            if not claimable:
                # Promote PENDING→READY where predecessors are satisfied.
                for node_id in ready_node_ids(graph, node_runs):
                    row = node_runs.get(node_id)
                    if row is not None and row.status == WorkflowNodeRunStatus.PENDING.value:
                        row.status = WorkflowNodeRunStatus.READY.value
                await self.db.flush()
                claimable = [
                    row
                    for row in (await self._node_map(tenant_id, run.id)).rows
                    if row.status == WorkflowNodeRunStatus.READY.value
                ]
                if not claimable:
                    break
                node_runs = await self._node_map(tenant_id, run.id)

            claimed_batch: list[WorkflowNodeRun] = []
            for row in claimable:
                claimed = await self.runs.claim_ready_node(
                    tenant_id=tenant_id,
                    workflow_run_id=run.id,
                    node_run_id=row.id,
                )
                if claimed is None:
                    continue
                enqueue_claimed_node(
                    tenant_id=tenant_id,
                    workflow_run_id=run.id,
                    node_run=claimed,
                )
                claimed_batch.append(claimed)

            if not claimed_batch:
                break

            await self.db.flush()
            if settings.WORKFLOW_INLINE_NODE_EXECUTION:
                await drain_inline_claimed_nodes(
                    self,
                    tenant_id=tenant_id,
                    run_id=run.id,
                    claimed=claimed_batch,
                )
                # Re-load run after inline drain (status may have changed).
                refreshed = await self.runs.get_run(tenant_id, run.id)
                if refreshed is not None:
                    run = refreshed
                if run.status in {
                    WorkflowRunStatus.SUCCEEDED.value,
                    WorkflowRunStatus.FAILED.value,
                    WorkflowRunStatus.CANCELLED.value,
                    WorkflowRunStatus.WAITING.value,
                }:
                    return run
                continue

            # Celery path: one advance pass claims/enqueues; workers call advance again.
            break

        node_runs = await self._node_map(tenant_id, run.id)
        finalize_run_status(run, node_runs)
        from backend.modules.workflows.occurrence_sync import sync_occurrence_for_run

        await sync_occurrence_for_run(self.db, run)
        await self.db.flush()
        return run

    async def _node_map(self, tenant_id: UUID, run_id: UUID) -> NodeRunIndex:
        rows = await self.runs.list_node_runs(tenant_id, run_id)
        return NodeRunIndex(rows)
