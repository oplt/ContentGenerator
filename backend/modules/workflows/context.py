"""Workflow execution context helpers (Phase 2)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.nodes.base import WorkflowNodeContext


def build_node_context(
    *,
    tenant_id: UUID,
    db: AsyncSession | None = None,
    correlation_id: str | None = None,
    workflow_run_id: UUID | None = None,
    automation_id: UUID | None = None,
    brand_id: UUID | None = None,
    node_id: str | None = None,
    node_run_id: UUID | None = None,
    resume_token: str | None = None,
    snapshot: dict[str, object] | None = None,
) -> WorkflowNodeContext:
    return WorkflowNodeContext(
        tenant_id=tenant_id,
        db=db,
        correlation_id=correlation_id,
        workflow_run_id=workflow_run_id,
        automation_id=automation_id,
        brand_id=brand_id,
        node_id=node_id,
        node_run_id=node_run_id,
        resume_token=resume_token,
        snapshot=dict(snapshot or {}),
    )
