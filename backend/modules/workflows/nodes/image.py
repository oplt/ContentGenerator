"""Image generation node — wraps ImageGenerationService."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.content_generation.image_service import ImageGenerationService
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.nodes.media_common import asset_output, require_db


class GenerateImageConfig(BaseModel):
    platform: str = "default"


class GenerateImageInput(BaseModel):
    content_job_id: UUID
    headline: str = Field(min_length=1)
    primary_topic: str = Field(default="general", min_length=1)
    keywords: str = ""


class GenerateImageOutput(BaseModel):
    asset_id: str | None = None
    public_url: str | None = None
    storage_key: str | None = None
    skipped: bool = False
    content_job_id: str | None = None
    mime_type: str | None = None


class GenerateImageNode(
    WorkflowNode[GenerateImageConfig, GenerateImageInput, GenerateImageOutput]
):
    type = "generate_image"
    version = 1
    category = "media"
    display_name = "Generate Image"
    description = "Wrap ImageGenerationService for content-job cover images."
    ConfigSchema = GenerateImageConfig
    InputSchema = GenerateImageInput
    OutputSchema = GenerateImageOutput
    required_capabilities = ["image"]
    input_ports = [
        NodePort(name="content_job_id", data_type="uuid"),
        NodePort(name="headline", data_type="string"),
        NodePort(name="primary_topic", data_type="string", required=False),
        NodePort(name="keywords", data_type="string", required=False),
    ]
    output_ports = [
        NodePort(name="asset_id", data_type="string", required=False),
        NodePort(name="public_url", data_type="string", required=False),
        NodePort(name="skipped", data_type="boolean"),
        NodePort(name="content_job_id", data_type="string", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        typed_in = GenerateImageInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateImageConfig.model_validate(config.model_dump())
        assert context.db is not None
        asset = await ImageGenerationService(context.db).generate_for_job(
            tenant_id=context.tenant_id,
            job_id=typed_in.content_job_id,
            headline=typed_in.headline,
            primary_topic=typed_in.primary_topic,
            keywords=typed_in.keywords,
            platform=typed_cfg.platform,
        )
        out = GenerateImageOutput.model_validate(
            asset_output(asset, content_job_id=typed_in.content_job_id)
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())
