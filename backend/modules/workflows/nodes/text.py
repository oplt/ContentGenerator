"""AI / text content nodes — LLM adapters (summarize / script / generate)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.modules.inference.providers import get_llm_provider
from backend.modules.video_pipeline.providers import get_video_providers
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)

# Re-export for existing imports.
from backend.modules.workflows.nodes.fact_review import FactReviewNode  # noqa: F401


class GenerateTextConfig(BaseModel):
    max_tokens: int = Field(default=800, ge=16, le=8000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    task: str = "default"
    tone: str | None = None


class GenerateTextInput(BaseModel):
    prompt: str = Field(min_length=1)
    system_hint: str | None = None


class GenerateTextOutput(BaseModel):
    text: str
    provider: str


class GenerateTextNode(WorkflowNode[GenerateTextConfig, GenerateTextInput, GenerateTextOutput]):
    """Low-level LLM adapter — raw AI text, not a ContentJob editorial artifact.

    For brand/risk/persistence policies use ``generate_canonical_content`` instead.
    """

    type = "generate_text"
    version = 1
    category = "ai_content"
    display_name = "Generate Text"
    description = (
        "Raw LLM text generation (reusable AI op). "
        "Does not create a ContentJob — use Generate Canonical Content for editorial artifacts."
    )
    ConfigSchema = GenerateTextConfig
    InputSchema = GenerateTextInput
    OutputSchema = GenerateTextOutput
    required_capabilities = ["llm"]
    input_ports = [
        NodePort(name="prompt", data_type="string"),
        NodePort(name="system_hint", data_type="string", required=False),
    ]
    output_ports = [
        NodePort(name="text", data_type="string"),
        NodePort(name="provider", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = GenerateTextInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateTextConfig.model_validate(config.model_dump())
        prompt = typed_in.prompt
        hints: list[str] = []
        if typed_cfg.tone:
            hints.append(f"Tone: {typed_cfg.tone.strip()}")
        if typed_in.system_hint:
            hints.append(typed_in.system_hint.strip())
        if hints:
            prompt = f"{'\n'.join(hints)}\n\n{prompt}"
        llm = get_llm_provider()
        text = await llm.generate_text(
            prompt,
            max_tokens=typed_cfg.max_tokens,
            temperature=typed_cfg.temperature,
            task=typed_cfg.task,
        )
        output = GenerateTextOutput(text=text, provider=getattr(llm, "provider_name", "unknown"))
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=output.model_dump())


class SummarizeConfig(BaseModel):
    max_words: int = Field(default=120, ge=10, le=2000)


class SummarizeInput(BaseModel):
    text: str = Field(min_length=1)


class SummarizeOutput(BaseModel):
    text: str
    provider: str


class SummarizeNode(WorkflowNode[SummarizeConfig, SummarizeInput, SummarizeOutput]):
    type = "summarize"
    version = 1
    category = "ai_content"
    display_name = "Summarize"
    description = "Summarize input text via inference providers."
    ConfigSchema = SummarizeConfig
    InputSchema = SummarizeInput
    OutputSchema = SummarizeOutput
    required_capabilities = ["llm"]
    input_ports = [NodePort(name="text", data_type="string")]
    output_ports = [
        NodePort(name="text", data_type="string"),
        NodePort(name="provider", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = SummarizeInput.model_validate(inputs.model_dump())
        typed_cfg = SummarizeConfig.model_validate(config.model_dump())
        llm = get_llm_provider()
        text = await llm.summarize(typed_in.text, max_words=typed_cfg.max_words)
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=SummarizeOutput(
                text=text, provider=getattr(llm, "provider_name", "unknown")
            ).model_dump(),
        )


class GenerateScriptConfig(BaseModel):
    tone: str = "urgent"
    max_words: int = Field(default=120, ge=20, le=500)


class GenerateScriptInput(BaseModel):
    digest: str | None = None
    headline: str | None = None
    summary: str = ""
    article_points: list[str] = Field(default_factory=list)


class GenerateScriptOutput(BaseModel):
    script: str
    digest: str


class GenerateScriptNode(WorkflowNode[GenerateScriptConfig, GenerateScriptInput, GenerateScriptOutput]):
    """Video-style script via video_pipeline ScriptProvider (LLM-backed)."""

    type = "generate_script"
    version = 1
    category = "ai_content"
    display_name = "Generate Script"
    description = "Generate a spoken/video script from digest or headline inputs."
    ConfigSchema = GenerateScriptConfig
    InputSchema = GenerateScriptInput
    OutputSchema = GenerateScriptOutput
    required_capabilities = ["llm"]
    input_ports = [
        NodePort(name="digest", data_type="string", required=False),
        NodePort(name="headline", data_type="string", required=False),
        NodePort(name="summary", data_type="string", required=False),
        NodePort(name="article_points", data_type="array", required=False),
    ]
    output_ports = [
        NodePort(name="script", data_type="string"),
        NodePort(name="digest", data_type="string"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = GenerateScriptInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateScriptConfig.model_validate(config.model_dump())
        research, script_provider, *_rest = get_video_providers()
        digest = (typed_in.digest or "").strip()
        if not digest:
            headline = (typed_in.headline or "").strip()
            if not headline:
                return NodeResult(
                    status=NodeResultStatus.FAILED,
                    error={
                        "code": "missing_script_source",
                        "message": "generate_script requires digest or headline",
                    },
                )
            digest = await research.build_digest(
                headline, typed_in.summary, list(typed_in.article_points)
            )
        script = await script_provider.build_script(digest, typed_cfg.tone)
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=GenerateScriptOutput(script=script, digest=digest).model_dump(),
        )
