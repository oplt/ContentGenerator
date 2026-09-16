"""Persistence for WorkflowRun / WorkflowNodeRun.

Claim lease helpers live in ``node_claiming`` and are re-exported here so Phase 0
gap tests can ``hasattr(run_repository, "claim_ready_node")``.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.node_claiming import (
    begin_node_execution,
    build_execution_key,
    claim_ready_node,
    complete_node,
    fail_node,
    list_stale_claimed_nodes,
    release_node_claim,
    renew_node_claim,
)
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun

__all__ = [
    "WorkflowRunRepository",
    "begin_node_execution",
    "build_execution_key",
    "claim_ready_node",
    "complete_node",
    "fail_node",
    "list_stale_claimed_nodes",
    "release_node_claim",
    "renew_node_claim",
]


class WorkflowRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_run(self, tenant_id: UUID, run_id: UUID) -> WorkflowRun | None:
        result = await self.db.execute(
            select(WorkflowRun).where(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_run_by_correlation(
        self, tenant_id: UUID, correlation_id: str
    ) -> WorkflowRun | None:
        result = await self.db.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.correlation_id == correlation_id,
            )
            .order_by(WorkflowRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self, tenant_id: UUID, *, limit: int = 50, status: str | None = None
    ) -> list[WorkflowRun]:
        stmt = select(WorkflowRun).where(WorkflowRun.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(WorkflowRun.status == status)
        stmt = stmt.order_by(WorkflowRun.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_run(self, run: WorkflowRun) -> WorkflowRun:
        self.db.add(run)
        await self.db.flush()
        return run

    async def list_node_runs(
        self, tenant_id: UUID, workflow_run_id: UUID
    ) -> list[WorkflowNodeRun]:
        result = await self.db.execute(
            select(WorkflowNodeRun)
            .where(
                WorkflowNodeRun.tenant_id == tenant_id,
                WorkflowNodeRun.workflow_run_id == workflow_run_id,
            )
            .order_by(WorkflowNodeRun.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_node_run(
        self, tenant_id: UUID, workflow_run_id: UUID, node_id: str
    ) -> WorkflowNodeRun | None:
        result = await self.db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.tenant_id == tenant_id,
                WorkflowNodeRun.workflow_run_id == workflow_run_id,
                WorkflowNodeRun.node_id == node_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_node_run_by_id(
        self, tenant_id: UUID, node_run_id: UUID
    ) -> WorkflowNodeRun | None:
        result = await self.db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.tenant_id == tenant_id,
                WorkflowNodeRun.id == node_run_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_node_run(self, node_run: WorkflowNodeRun) -> WorkflowNodeRun:
        self.db.add(node_run)
        await self.db.flush()
        return node_run

    async def get_by_resume_token(
        self, tenant_id: UUID, resume_token: str
    ) -> WorkflowNodeRun | None:
        result = await self.db.execute(
            select(WorkflowNodeRun).where(
                WorkflowNodeRun.tenant_id == tenant_id,
                WorkflowNodeRun.resume_token == resume_token,
            )
        )
        return result.scalar_one_or_none()

    async def claim_ready_node(
        self,
        *,
        tenant_id: UUID,
        workflow_run_id: UUID,
        node_run_id: UUID | None = None,
        lease_seconds: int | None = None,
    ) -> WorkflowNodeRun | None:
        return await claim_ready_node(
            self.db,
            tenant_id=tenant_id,
            workflow_run_id=workflow_run_id,
            node_run_id=node_run_id,
            lease_seconds=lease_seconds,
        )
