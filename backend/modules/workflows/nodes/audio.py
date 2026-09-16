"""TTS node — wraps TTSService."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.content_generation.tts_service import TTSService
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.nodes.media_common import asset_output, require_db


class GenerateTTSConfig(BaseModel):
    platform: str = "default"
    cta_default: str = "Follow for more updates."


class GenerateTTSInput(BaseModel):
    content_job_id: UUID
    headline: str = Field(min_length=1)
    summary: str = ""
    cta: str = ""


class GenerateTTSOutput(BaseModel):
    asset_id: str | None = None
    public_url: str | None = None
    storage_key: str | None = None
    skipped: bool = False
    content_job_id: str | None = None
    mime_type: str | None = None


class GenerateTTSNode(WorkflowNode[GenerateTTSConfig, GenerateTTSInput, GenerateTTSOutput]):
    type = "generate_tts"
    version = 1
    category = "media"
    display_name = "Generate TTS"
    description = "Wrap TTSService for content-job voiceovers."
    ConfigSchema = GenerateTTSConfig
    InputSchema = GenerateTTSInput
    OutputSchema = GenerateTTSOutput
    required_capabilities = ["tts"]
    input_ports = [
        NodePort(name="content_job_id", data_type="uuid"),
        NodePort(name="headline", data_type="string"),
        NodePort(name="summary", data_type="string", required=False),
        NodePort(name="cta", data_type="string", required=False),
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
        typed_in = GenerateTTSInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateTTSConfig.model_validate(config.model_dump())
        assert context.db is not None
        cta = typed_in.cta.strip() or typed_cfg.cta_default
        asset = await TTSService(context.db).generate_for_job(
            tenant_id=context.tenant_id,
            job_id=typed_in.content_job_id,
            headline=typed_in.headline,
            summary=typed_in.summary,
            cta=cta,
            platform=typed_cfg.platform,
        )
        out = GenerateTTSOutput.model_validate(
            asset_output(asset, content_job_id=typed_in.content_job_id)
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())
