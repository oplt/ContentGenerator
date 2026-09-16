"""Human approval node — pauses workflow via ApprovalService + channel delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.workflows.approval_binding import (
    WORKFLOW_BINDING_KEY,
    build_workflow_binding,
)
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class ApprovalConfig(BaseModel):
    required: bool = True
    channels: list[str] = Field(default_factory=lambda: ["in_app", "telegram"])
    timeout_seconds: int = Field(default=86400, ge=60)
    on_timeout: str = Field(default="stop")
    allow_revision: bool = True
    recipient: str | None = None


class ApprovalInput(BaseModel):
    content_job_id: UUID


class ApprovalOutput(BaseModel):
    approval_request_id: UUID | None = None
    status: str
    channels: list[str] = Field(default_factory=list)
    content_job_id: UUID | None = None
    revision_count: int = 0


class ApprovalNode(WorkflowNode[ApprovalConfig, ApprovalInput, ApprovalOutput]):
    type = "approval"
    version = 1
    category = "human"
    display_name = "Approval"
    description = "Create/refresh an approval request and pause until a human decision."
    ConfigSchema = ApprovalConfig
    InputSchema = ApprovalInput
    OutputSchema = ApprovalOutput
    may_pause = True
    input_ports = [NodePort(name="content_job_id", data_type="uuid")]
    output_ports = [
        NodePort(name="approval_request_id", data_type="uuid", required=False),
        NodePort(name="status", data_type="string"),
        NodePort(name="channels", data_type="array"),
        NodePort(name="content_job_id", data_type="uuid", required=False),
        NodePort(name="revision_count", data_type="number", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        if context.db is None:
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={"code": "missing_db", "message": "ApprovalNode requires a DB session"},
            )
        typed_in = ApprovalInput.model_validate(inputs.model_dump())
        typed_cfg = ApprovalConfig.model_validate(config.model_dump())

        # 9.1 — required=false: non-blocking. SUCCEEDED + status not_required.
        if not typed_cfg.required:
            output = ApprovalOutput(
                approval_request_id=None,
                status="not_required",
                channels=[],
                content_job_id=typed_in.content_job_id,
                revision_count=0,
            )
            return NodeResult(
                status=NodeResultStatus.SUCCEEDED,
                output=output.model_dump(mode="json"),
            )

        # Idempotent redelivery: reuse approval already created for this node run.
        if context.node_run_id is not None:
            from backend.modules.workflows.run_models import WorkflowNodeRun

            existing = await context.db.get(WorkflowNodeRun, context.node_run_id)
            prior = dict(existing.output_json or {}) if existing is not None else {}
            prior_id = prior.get("approval_request_id")
            if prior_id:
                return NodeResult(
                    status=NodeResultStatus.WAITING,
                    output={
                        "approval_request_id": prior_id,
                        "status": str(prior.get("status") or "pending"),
                        "channels": list(
                            cast(list[str], prior.get("channels") or typed_cfg.channels)
                        ),
                        "content_job_id": str(
                            prior.get("content_job_id") or typed_in.content_job_id
                        ),
                        "revision_count": int(str(prior.get("revision_count") or 0)),
                        "timeout_seconds": typed_cfg.timeout_seconds,
                        "on_timeout": typed_cfg.on_timeout,
                    },
                    waiting_reason="approval_pending",
                )

        from backend.modules.approvals.service import ApprovalService
        from backend.modules.workflows.approval_delivery import ApprovalDeliveryService

        svc = ApprovalService(context.db)
        request = await svc.send_for_approval(
            tenant_id=context.tenant_id,
            content_job_id=typed_in.content_job_id,
            recipient=typed_cfg.recipient,
            channels=list(typed_cfg.channels),
            deliver=False,
        )

        delivered = await ApprovalDeliveryService().deliver(
            svc,
            request,
            tenant_id=context.tenant_id,
            content_job_id=typed_in.content_job_id,
            channels=list(typed_cfg.channels),
        )

        binding = None
        if context.resume_token:
            binding = build_workflow_binding(
                workflow_run_id=context.workflow_run_id,
                workflow_node_run_id=context.node_run_id,
                node_id=context.node_id,
                resume_token=context.resume_token,
                on_timeout=typed_cfg.on_timeout,
                allow_revision=typed_cfg.allow_revision,
                channels=list(typed_cfg.channels),
            )
            payload = dict(request.response_payload_json or {})
            payload[WORKFLOW_BINDING_KEY] = binding
            request.response_payload_json = payload
            request.expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=typed_cfg.timeout_seconds
            )
            await context.db.flush()

        output = ApprovalOutput(
            approval_request_id=request.id,
            status=str(request.status),
            channels=list(delivered or typed_cfg.channels),
            content_job_id=typed_in.content_job_id,
            revision_count=int(request.revision_count or 0),
        )
        return NodeResult(
            status=NodeResultStatus.WAITING,
            output={
                **output.model_dump(mode="json"),
                "timeout_seconds": typed_cfg.timeout_seconds,
                "on_timeout": typed_cfg.on_timeout,
            },
            waiting_reason="approval_pending",
        )
