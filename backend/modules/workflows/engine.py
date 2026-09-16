"""Minimal linear workflow engine. READY nodes in-process; WAITING does not hold workers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.capability_context import enrich_compile_context_from_db
from backend.modules.workflows.compiler import WorkflowCompiler
from backend.modules.workflows.config_resolver import ConfigResolver
from backend.modules.workflows.engine_execute import execute_ready_node
from backend.modules.workflows.engine_ready import (
    ready_node_ids,
    root_node_ids,
    run_has_failure,
    run_is_waiting,
)
from backend.modules.workflows.engine_status import as_dict, finalize_run_status
from backend.modules.workflows.graph_schema import CompileContext, WorkflowGraph
from backend.modules.workflows.registry import WorkflowNodeRegistry, get_default_registry
from backend.modules.workflows.repository import WorkflowRepository
from backend.modules.workflows.run_models import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from backend.modules.workflows.run_repository import WorkflowRunRepository
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
        compile_context: CompileContext | None = None,
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

        compile_context = await enrich_compile_context_from_db(
            self.db, compile_context, tenant_id=tenant_id
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
        node_runs = await self._node_map(tenant_id, run.id)
        graph_nodes = {n.id: n for n in graph.nodes}
        snapshot = as_dict(run.context_snapshot)
        node_outputs: dict[str, Any] = as_dict(snapshot.get("node_outputs"))
        initial_inputs = as_dict(snapshot.get("initial_inputs"))

        for _ in range(max(1, len(graph.nodes) * 2)):
            if run_is_waiting(node_runs) or run_has_failure(node_runs):
                break
            ready = ready_node_ids(graph, node_runs)
            if not ready:
                break
            for node_id in ready:
                await execute_ready_node(
                    self,
                    run=run,
                    graph_node=graph_nodes[node_id],
                    node_run=node_runs[node_id],
                    graph=graph,
                    node_runs=node_runs,
                    node_outputs=node_outputs,
                    initial_inputs=initial_inputs,
                )
                if node_runs[node_id].status == WorkflowNodeRunStatus.WAITING.value:
                    break
                if node_runs[node_id].status == WorkflowNodeRunStatus.FAILED.value:
                    break
            else:
                continue
            break

        snapshot["node_outputs"] = node_outputs
        run.context_snapshot = snapshot
        finalize_run_status(run, node_runs)
        await self.db.flush()
        return run

    async def _node_map(self, tenant_id: UUID, run_id: UUID) -> dict[str, WorkflowNodeRun]:
        rows = await self.runs.list_node_runs(tenant_id, run_id)
        return {row.node_id: row for row in rows}
