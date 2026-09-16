"""Persistence for WorkflowRun / WorkflowNodeRun."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun


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
