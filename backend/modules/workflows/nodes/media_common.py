"""Shared helpers for media/content workflow nodes (Phase 11)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from backend.modules.workflows.nodes.base import NodeResult, NodeResultStatus, WorkflowNodeContext


def require_db(context: WorkflowNodeContext) -> NodeResult | None:
    if context.db is None:
        return NodeResult(
            status=NodeResultStatus.FAILED,
            error={
                "code": "missing_db",
                "message": "Node requires a database session on WorkflowNodeContext",
            },
        )
    return None


def asset_output(asset: Any | None, *, content_job_id: UUID | None = None) -> dict[str, Any]:
    if asset is None:
        return {
            "asset_id": None,
            "public_url": None,
            "storage_key": None,
            "skipped": True,
            "content_job_id": str(content_job_id) if content_job_id else None,
        }
    return {
        "asset_id": str(getattr(asset, "id", None) or ""),
        "public_url": getattr(asset, "public_url", None),
        "storage_key": getattr(asset, "storage_key", None),
        "skipped": False,
        "content_job_id": str(getattr(asset, "content_job_id", content_job_id) or ""),
        "mime_type": getattr(asset, "mime_type", None),
    }


def fail(code: str, message: str) -> NodeResult:
    return NodeResult(
        status=NodeResultStatus.FAILED,
        error={"code": code, "message": message},
    )
