"""Approval → workflow resume bridge (Phase 6).

Stores binding on ApprovalRequest.response_payload_json["workflow"] so channel
handlers stay channel-agnostic (Telegram/WhatsApp/in-app).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.approvals.models import ApprovalRequest, ApprovalStatus

WORKFLOW_BINDING_KEY = "workflow"

_STATUS_OUTCOME = {
    ApprovalStatus.APPROVED.value: "approved",
    ApprovalStatus.REJECTED.value: "rejected",
    ApprovalStatus.EXPIRED.value: "expired",
}


def get_workflow_binding(request: ApprovalRequest) -> dict[str, Any] | None:
    payload = request.response_payload_json or {}
    binding = payload.get(WORKFLOW_BINDING_KEY)
    if isinstance(binding, dict) and binding.get("resume_token"):
        return dict(binding)
    return None


def build_workflow_binding(
    *,
    workflow_run_id: UUID | None,
    workflow_node_run_id: UUID | None,
    node_id: str | None,
    resume_token: str | None,
    on_timeout: str = "stop",
    allow_revision: bool = True,
    channels: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "workflow_run_id": str(workflow_run_id) if workflow_run_id else None,
        "workflow_node_run_id": str(workflow_node_run_id) if workflow_node_run_id else None,
        "node_id": node_id,
        "resume_token": resume_token,
        "on_timeout": on_timeout,
        "allow_revision": allow_revision,
        "channels": list(channels or []),
    }


async def maybe_resume_workflow_from_approval(
    db: AsyncSession, request: ApprovalRequest
) -> Any | None:
    """Resume WAITING node after a terminal approval decision. No-op if unbound."""
    binding = get_workflow_binding(request)
    if binding is None:
        return None
    outcome = _STATUS_OUTCOME.get(str(request.status))
    if outcome is None:
        return None

    from backend.modules.workflows.engine import WorkflowEngine
    from backend.modules.workflows.engine_resume import resume_waiting_node

    engine = WorkflowEngine(db)
    return await resume_waiting_node(
        engine,
        request.tenant_id,
        resume_token=str(binding["resume_token"]),
        outcome=outcome,
        decision={
            "approval_request_id": str(request.id),
            "status": str(request.status),
            "on_timeout": binding.get("on_timeout", "stop"),
        },
    )
