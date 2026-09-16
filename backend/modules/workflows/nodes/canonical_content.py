"""GenerateCanonicalContent — domain ContentJob orchestration (Phase 11).

Distinct from GenerateText (raw LLM). This node wraps ContentGenerationService so
brand/prompt/risk/persistence policies stay in the content-generation domain.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    NodeImplementationStatus,
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class GenerateCanonicalContentConfig(BaseModel):
    """Thin config — domain policies live in ContentGenerationService."""

    pass


class GenerateCanonicalContentInput(BaseModel):
    content_plan_id: UUID
    social_account_ids: list[UUID] | None = None
    feedback: str | None = None
    revision_of_job_id: UUID | None = None


class GenerateCanonicalContentOutput(BaseModel):
    content_job_id: UUID
    content_plan_id: UUID
    text: str
    status: str
    risk_label: str | None = None
    asset_group_id: UUID | None = None
    target_social_account_ids: list[str] = Field(default_factory=list)
    provider: str = "content_generation"


class GenerateCanonicalContentNode(
    WorkflowNode[
        GenerateCanonicalContentConfig,
        GenerateCanonicalContentInput,
        GenerateCanonicalContentOutput,
    ]
):
    """Create durable editorial ContentJob via existing generation orchestration."""

    type = "generate_canonical_content"
    version = 1
    category = "ai_content"
    display_name = "Generate Canonical Content"
    description = (
        "Run ContentGenerationService for a content plan — produces a ContentJob "
        "(editorial artifact), not raw LLM text."
    )
    implementation_status = NodeImplementationStatus.BETA
    ConfigSchema = GenerateCanonicalContentConfig
    InputSchema = GenerateCanonicalContentInput
    OutputSchema = GenerateCanonicalContentOutput
    required_capabilities = ["llm"]
    input_ports = [
        NodePort(name="content_plan_id", data_type="uuid"),
        NodePort(name="social_account_ids", data_type="array", required=False),
        NodePort(name="feedback", data_type="string", required=False),
        NodePort(name="revision_of_job_id", data_type="uuid", required=False),
    ]
    output_ports = [
        NodePort(name="content_job_id", data_type="uuid"),
        NodePort(name="content_plan_id", data_type="uuid"),
        NodePort(name="text", data_type="string"),
        NodePort(name="status", data_type="string"),
        NodePort(name="risk_label", data_type="string", required=False),
        NodePort(name="asset_group_id", data_type="uuid", required=False),
        NodePort(name="target_social_account_ids", data_type="array", required=False),
        NodePort(name="provider", data_type="string", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = config
        if context.db is None:
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "missing_db",
                    "message": "GenerateCanonicalContent requires a DB session",
                },
            )
        typed_in = GenerateCanonicalContentInput.model_validate(inputs.model_dump())

        from backend.modules.content_generation.canonical import (
            canonical_primary_platform,
            extract_canonical_text,
        )
        from backend.modules.content_generation.service import ContentGenerationService

        svc = ContentGenerationService(context.db)
        try:
            job = await svc.generate(
                tenant_id=context.tenant_id,
                plan_id=typed_in.content_plan_id,
                feedback=typed_in.feedback,
                revision_of_job_id=typed_in.revision_of_job_id,
                social_account_ids=typed_in.social_account_ids,
            )
        except HTTPException as exc:
            detail = exc.detail
            message = detail if isinstance(detail, str) else str(detail)
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "content_generation_failed",
                    "message": message,
                    "status_code": exc.status_code,
                },
            )
        except Exception as exc:  # noqa: BLE001 — surface domain failures to the engine
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "content_generation_error",
                    "message": str(exc) or exc.__class__.__name__,
                },
            )

        assets = await svc.repo.list_assets(job.id)
        primary = canonical_primary_platform(job)
        text = extract_canonical_text(assets, primary_platform=primary) or ""
        # Stamp for downstream nodes / debugging without inventing a parallel store.
        grounding = dict(job.grounding_bundle or {})
        if text and grounding.get("canonical_text") != text:
            grounding["canonical_text"] = text
            job.grounding_bundle = grounding
            await context.db.flush()

        asset_group = await svc.repo.get_asset_group_for_job(job.id)
        risk_label = None
        if isinstance(job.grounding_bundle, dict):
            raw = job.grounding_bundle.get("risk_label")
            risk_label = str(raw) if raw is not None else None

        output = GenerateCanonicalContentOutput(
            content_job_id=job.id,
            content_plan_id=job.content_plan_id,
            text=text,
            status=str(job.status),
            risk_label=risk_label,
            asset_group_id=asset_group.id if asset_group else None,
            target_social_account_ids=list(job.target_social_account_ids or []),
        )
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
        )
