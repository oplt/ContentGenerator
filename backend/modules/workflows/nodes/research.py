"""ResearchSources — wrap source ingestion + story intelligence (Phase 12)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from backend.modules.workflows.nodes.base import (
    NodeImplementationStatus,
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class ResearchSourcesConfig(BaseModel):
    """Thin config — ingestion policy stays in SourceIngestionService."""

    pass


class ResearchSourcesInput(BaseModel):
    source_id: UUID
    # When true, skip clustering LLM stage if the ingestion workflow supports it.
    # Reserved for service flags; default runs full ingestion.
    include_clustering: bool = True


class ResearchSourcesOutput(BaseModel):
    source_id: UUID
    status: str
    raw_articles_ingested: int = 0
    clusters_updated: int = 0
    fetch_run_id: UUID | None = None
    task_id: str | None = None


class ResearchSourcesNode(
    WorkflowNode[ResearchSourcesConfig, ResearchSourcesInput, ResearchSourcesOutput]
):
    """Trigger tenant source ingestion via SourceIngestionService."""

    type = "research_sources"
    version = 1
    category = "sources"
    display_name = "Research Sources"
    description = (
        "Run source ingestion for a configured source (fetch + persist + clustering)."
    )
    implementation_status = NodeImplementationStatus.STABLE
    ConfigSchema = ResearchSourcesConfig
    InputSchema = ResearchSourcesInput
    OutputSchema = ResearchSourcesOutput
    required_capabilities = []
    input_ports = [
        NodePort(name="source_id", data_type="uuid"),
        NodePort(name="include_clustering", data_type="boolean", required=False),
    ]
    output_ports = [
        NodePort(name="source_id", data_type="uuid"),
        NodePort(name="status", data_type="string"),
        NodePort(name="raw_articles_ingested", data_type="number"),
        NodePort(name="clusters_updated", data_type="number"),
        NodePort(name="fetch_run_id", data_type="uuid", required=False),
        NodePort(name="task_id", data_type="string", required=False),
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
                error={"code": "missing_db", "message": "ResearchSources requires a DB session"},
            )
        typed_in = ResearchSourcesInput.model_validate(inputs.model_dump())
        _ = typed_in.include_clustering  # reserved — full workflow always clusters today

        from backend.modules.source_ingestion.service import SourceIngestionService

        try:
            result = await SourceIngestionService(context.db).run_ingestion(
                tenant_id=context.tenant_id,
                source_id=typed_in.source_id,
            )
        except HTTPException as exc:
            detail = exc.detail
            message = detail if isinstance(detail, str) else str(detail)
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "research_sources_failed",
                    "message": message,
                    "status_code": exc.status_code,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status=NodeResultStatus.FAILED,
                error={
                    "code": "research_sources_error",
                    "message": str(exc) or exc.__class__.__name__,
                },
            )

        output = ResearchSourcesOutput(
            source_id=result.source_id,
            status=str(result.status),
            raw_articles_ingested=int(result.raw_articles_ingested or 0),
            clusters_updated=int(result.clusters_updated or 0),
            fetch_run_id=result.fetch_run_id,
            task_id=result.task_id,
        )
        return NodeResult(
            status=NodeResultStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
        )
