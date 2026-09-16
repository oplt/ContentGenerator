"""Human approval node — pauses workflow via existing ApprovalService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    approval_request_id: UUID
    status: str
    channels: list[str]


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
        NodePort(name="approval_request_id", data_type="uuid"),
        NodePort(name="status", data_type="string"),
        NodePort(name="channels", data_type="array"),
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

        # Local import keeps router/registry import graph free of approval side effects.
        from backend.modules.approvals.service import ApprovalService

        request = await ApprovalService(context.db).send_for_approval(
            tenant_id=context.tenant_id,
            content_job_id=typed_in.content_job_id,
            recipient=typed_cfg.recipient,
        )

        # Bind workflow identity for durable resume (channel-agnostic).
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
            channels=list(typed_cfg.channels),
        )
        return NodeResult(
            status=NodeResultStatus.WAITING,
            output=output.model_dump(mode="json"),
            waiting_reason="approval_pending",
        )
