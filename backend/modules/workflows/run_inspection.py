"""Build redacted operator inspection payloads for workflow runs (Phase 15)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_strategy.models import Brand
from backend.modules.workflows.models import Automation, WorkflowVersion
from backend.modules.workflows.payload_redact import redact_value
from backend.modules.workflows.run_models import WorkflowNodeRun, WorkflowRun
from backend.modules.workflows.schemas import (
    WorkflowNodeRunResponse,
    WorkflowRunDetailResponse,
    WorkflowRunInspectionMeta,
    WorkflowRunResponse,
)


def _duration_ms(node: WorkflowNodeRun) -> int | None:
    if node.started_at is None or node.finished_at is None:
        return None
    delta = node.finished_at - node.started_at
    return max(0, int(delta.total_seconds() * 1000))


def serialize_node_run(node: WorkflowNodeRun) -> WorkflowNodeRunResponse:
    payload = WorkflowNodeRunResponse.model_validate(node)
    data = payload.model_dump()
    data["input_json"] = redact_value(data.get("input_json") or {})
    data["output_json"] = redact_value(data.get("output_json") or {})
    if data.get("error_json") is not None:
        data["error_json"] = redact_value(data["error_json"])
    # Never expose live lease / resume secrets on GET inspection.
    data["resume_token"] = None
    data["claim_token"] = None
    data["duration_ms"] = _duration_ms(node)
    data["can_resume"] = node.status == "waiting" and bool(node.resume_token)
    data["can_retry"] = node.status == "failed"
    return WorkflowNodeRunResponse.model_validate(data)


def serialize_run(run: WorkflowRun) -> WorkflowRunResponse:
    payload = WorkflowRunResponse.model_validate(run)
    data = payload.model_dump()
    data["trigger_payload"] = redact_value(data.get("trigger_payload") or {})
    data["context_snapshot"] = redact_value(data.get("context_snapshot") or {})
    return WorkflowRunResponse.model_validate(data)


async def load_inspection_meta(
    db: AsyncSession, run: WorkflowRun
) -> WorkflowRunInspectionMeta:
    version_number: int | None = None
    automation_name: str | None = None
    brand_name: str | None = None

    version = await db.get(WorkflowVersion, run.workflow_version_id)
    if version is not None:
        version_number = int(version.version)

    if run.automation_id is not None:
        automation = await db.get(Automation, run.automation_id)
        if automation is not None:
            automation_name = str(automation.name)

    if run.brand_id is not None:
        brand = await db.get(Brand, run.brand_id)
        if brand is not None:
            brand_name = str(brand.name)

    return WorkflowRunInspectionMeta(
        version_number=version_number,
        automation_name=automation_name,
        brand_name=brand_name,
    )


async def build_run_detail(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    nodes: list[WorkflowNodeRun],
) -> WorkflowRunDetailResponse:
    meta = await load_inspection_meta(db, run)
    return WorkflowRunDetailResponse(
        run=serialize_run(run),
        nodes=[serialize_node_run(node) for node in nodes],
        meta=meta,
    )
