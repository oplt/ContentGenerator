"""Distribution / publishing nodes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class PublishConfig(BaseModel):
    dry_run: bool = True
    platforms: list[str] | None = None


class PublishInput(BaseModel):
    content_job_id: UUID
    social_account_ids: list[UUID] | None = None
    content_variant_ids: list[UUID] | None = None
    approval_request_id: UUID | None = None
    scheduled_for: datetime | None = None
    idempotency_key: str | None = Field(default=None, min_length=8)


class PublishOutput(BaseModel):
    job_ids: list[UUID]
    statuses: list[str]
    dry_run: bool
    content_variant_ids: list[UUID] = Field(default_factory=list)


class PublishNode(WorkflowNode[PublishConfig, PublishInput, PublishOutput]):
    type = "publish"
    version = 1
    category = "distribution"
    display_name = "Publish"
    description = "Enqueue publishing jobs via existing PublishingService (dry-run by default)."
    ConfigSchema = PublishConfig
    InputSchema = PublishInput
    OutputSchema = PublishOutput
    required_capabilities = ["publish"]
    input_ports = [
        NodePort(name="content_job_id", data_type="uuid"),
        NodePort(name="social_account_ids", data_type="array", required=False),
        NodePort(name="content_variant_ids", data_type="array", required=False),
        NodePort(name="approval_request_id", data_type="uuid", required=False),
    ]
    output_ports = [
        NodePort(name="job_ids", data_type="array"),
        NodePort(name="statuses", data_type="array"),
        NodePort(name="dry_run", data_type="boolean"),
        NodePort(name="content_variant_ids", data_type="array"),
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
                error={"code": "missing_db", "message": "PublishNode requires a DB session"},
            )
        typed_in = PublishInput.model_validate(inputs.model_dump())
        typed_cfg = PublishConfig.model_validate(config.model_dump())

        from backend.modules.publishing.schemas import PublishNowRequest
        from backend.modules.publishing.service import PublishingService

        payload = PublishNowRequest(
            content_job_id=typed_in.content_job_id,
            platforms=typed_cfg.platforms,
            social_account_ids=typed_in.social_account_ids,
            content_variant_ids=typed_in.content_variant_ids,
            scheduled_for=typed_in.scheduled_for,
            dry_run=typed_cfg.dry_run,
            idempotency_key=typed_in.idempotency_key,
        )
        jobs = await PublishingService(context.db).publish_now(
            tenant_id=context.tenant_id,
            approval_request_id=typed_in.approval_request_id,
            payload=payload,
        )
        used_variant_ids: list[UUID] = []
        seen: set[UUID] = set()
        for job in jobs:
            raw = getattr(job, "content_variant_id", None)
            if not isinstance(raw, UUID):
                continue
            if raw in seen:
                continue
            seen.add(raw)
            used_variant_ids.append(raw)
        used_variant_ids.sort(key=str)
        output = PublishOutput(
            job_ids=[job.id for job in jobs],
            statuses=[str(job.status) for job in jobs],
            dry_run=typed_cfg.dry_run,
            content_variant_ids=used_variant_ids,
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=output.model_dump(mode="json"))
