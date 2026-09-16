"""Generic video node — wraps video_pipeline providers / VideoPipelineService."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from backend.modules.content_generation.models import ContentJob
from backend.modules.story_intelligence.models import StoryCluster
from backend.modules.video_pipeline.providers import get_video_providers
from backend.modules.video_pipeline.service import VideoPipelineService
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.nodes.media_common import fail, require_db


class GenerateVideoConfig(BaseModel):
    mode: str = Field(default="script_pipeline", pattern="^(script_pipeline|full_pipeline)$")
    tone: str = "urgent"


class GenerateVideoInput(BaseModel):
    headline: str | None = None
    summary: str = ""
    article_points: list[str] = Field(default_factory=list)
    script: str | None = None
    content_job_id: UUID | None = None
    cluster_id: UUID | None = None


class GenerateVideoOutput(BaseModel):
    script: str
    digest: str = ""
    storyboard: str = ""
    captions: str = ""
    content_job_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    mode: str


class GenerateVideoNode(
    WorkflowNode[GenerateVideoConfig, GenerateVideoInput, GenerateVideoOutput]
):
    type = "generate_video"
    version = 1
    category = "media"
    display_name = "Generate Video"
    description = "Wrap video_pipeline (script stages or full ContentJob pipeline)."
    ConfigSchema = GenerateVideoConfig
    InputSchema = GenerateVideoInput
    OutputSchema = GenerateVideoOutput
    required_capabilities = ["video"]
    input_ports = [
        NodePort(name="headline", data_type="string", required=False),
        NodePort(name="summary", data_type="string", required=False),
        NodePort(name="script", data_type="string", required=False),
        NodePort(name="content_job_id", data_type="uuid", required=False),
        NodePort(name="cluster_id", data_type="uuid", required=False),
        NodePort(name="article_points", data_type="array", required=False),
    ]
    output_ports = [
        NodePort(name="script", data_type="string"),
        NodePort(name="digest", data_type="string", required=False),
        NodePort(name="storyboard", data_type="string", required=False),
        NodePort(name="captions", data_type="string", required=False),
        NodePort(name="asset_ids", data_type="array", required=False),
        NodePort(name="content_job_id", data_type="string", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        typed_in = GenerateVideoInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateVideoConfig.model_validate(config.model_dump())
        if typed_cfg.mode == "full_pipeline":
            return await self._full_pipeline(context, typed_in, typed_cfg)
        return await self._script_pipeline(typed_in, typed_cfg)

    async def _script_pipeline(
        self, typed_in: GenerateVideoInput, typed_cfg: GenerateVideoConfig
    ) -> NodeResult:
        research, script_provider, visual, _voice, captions_provider, _render = (
            get_video_providers()
        )
        script = (typed_in.script or "").strip()
        digest = ""
        if not script:
            headline = (typed_in.headline or "").strip()
            if not headline:
                return fail(
                    "missing_video_source",
                    "generate_video script_pipeline requires script or headline",
                )
            digest = await research.build_digest(
                headline, typed_in.summary, list(typed_in.article_points)
            )
            script = await script_provider.build_script(digest, typed_cfg.tone)
        storyboard = await visual.build_storyboard(script)
        captions = await captions_provider.build_captions(script)
        out = GenerateVideoOutput(
            script=script,
            digest=digest,
            storyboard=storyboard,
            captions=captions,
            content_job_id=str(typed_in.content_job_id) if typed_in.content_job_id else None,
            mode=typed_cfg.mode,
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())

    async def _full_pipeline(
        self,
        context: WorkflowNodeContext,
        typed_in: GenerateVideoInput,
        typed_cfg: GenerateVideoConfig,
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        if typed_in.content_job_id is None or typed_in.cluster_id is None:
            return fail(
                "missing_pipeline_ids",
                "full_pipeline mode requires content_job_id and cluster_id",
            )
        assert context.db is not None
        job = await context.db.get(ContentJob, typed_in.content_job_id)
        cluster = await context.db.get(StoryCluster, typed_in.cluster_id)
        if job is None or cluster is None:
            return fail("not_found", "ContentJob or StoryCluster not found")
        if job.tenant_id != context.tenant_id:
            return fail("tenant_mismatch", "ContentJob tenant mismatch")
        assets = await VideoPipelineService(context.db).run(job=job, cluster=cluster)
        script_text = ""
        for asset in assets:
            if asset.asset_type == "script" and asset.text_content:
                script_text = asset.text_content
                break
        out = GenerateVideoOutput(
            script=script_text or (typed_in.script or ""),
            content_job_id=str(typed_in.content_job_id),
            asset_ids=[str(a.id) for a in assets],
            mode=typed_cfg.mode,
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())
