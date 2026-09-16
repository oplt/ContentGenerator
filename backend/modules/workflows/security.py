"""Workflow security helpers (Phase 17): secret scrubbing + account authz."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.account_selection import assert_accounts_authorized
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.workflows.config_merge import strip_secrets
from backend.modules.workflows.graph_schema import WorkflowGraph


def sanitize_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(strip_secrets(dict(value or {})))


def sanitize_workflow_graph(graph: WorkflowGraph | dict[str, Any]) -> WorkflowGraph:
    """Drop secret-looking keys from node configs + metadata before persist."""
    parsed = graph if isinstance(graph, WorkflowGraph) else WorkflowGraph.model_validate(graph)
    payload = parsed.model_dump(mode="json")
    nodes = []
    for node in payload.get("nodes") or []:
        node = dict(node)
        node["config"] = sanitize_mapping(node.get("config"))
        nodes.append(node)
    payload["nodes"] = nodes
    payload["metadata"] = sanitize_mapping(payload.get("metadata"))
    return WorkflowGraph.model_validate(payload)


async def authorize_social_account_ids(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    social_account_ids: list[UUID],
) -> None:
    """Ensure selected targets exist for tenant and are not quarantined."""
    if not social_account_ids:
        return
    repo = PublishingRepository(db)
    found = await repo.get_social_accounts_by_ids(tenant_id, social_account_ids)
    assert_accounts_authorized(
        tenant_id=tenant_id,
        requested_ids=list(social_account_ids),
        found=found,
    )
