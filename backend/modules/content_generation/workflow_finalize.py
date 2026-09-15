from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_generation.models import (
    ContentJob,
    ContentJobStatus,
    GeneratedAssetGroup,
    GeneratedAssetGroupStatus,
    VideoStage,
)
from backend.modules.content_strategy.models import ContentFormat
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.video_pipeline.service import VideoPipelineService


class _FinalizeDeps(Protocol):
    db: AsyncSession
    audit: AuditService
    video_pipeline: VideoPipelineService


async def _finalize_generation(
    svc: _FinalizeDeps,
    *,
    tenant_id: UUID,
    job: ContentJob,
    asset_group: GeneratedAssetGroup,
    cluster: Any,
    plan: Any,
    originality_report: dict[str, object],
    policy_payload: dict[str, object],
    primary_platform: str,
) -> ContentJob:
    from backend.workers.task_defs.generation import (
        generate_image_asset_task,
        generate_tts_asset_task,
    )

    generate_image_asset_task.delay(
        tenant_id=str(tenant_id),
        job_id=str(job.id),
        headline=cluster.headline,
        primary_topic=cluster.primary_topic,
        keywords=cluster.explainability.get("keywords", ""),
        platform=primary_platform,
    )
    generate_tts_asset_task.delay(
        tenant_id=str(tenant_id),
        job_id=str(job.id),
        headline=cluster.headline,
        summary=cluster.summary or "",
        cta=plan.recommended_cta or "",
        platform=primary_platform,
    )
    job.stage = VideoStage.COLLECTING_ASSETS.value
    job.progress = 70
    job.provider_metadata = {
        **(job.provider_metadata or {}),
        "pipeline_stage": "image_tts_enqueued",
        "stage_idempotency_key": f"content-job:{job.id}:image_tts",
    }

    if plan.content_format in {ContentFormat.VIDEO.value, ContentFormat.BOTH.value}:
        job.stage = VideoStage.RESEARCHING.value
        job.progress = 35
        await svc.video_pipeline.run(job=job, cluster=cluster)

    job.status = ContentJobStatus.COMPLETED.value
    job.stage = VideoStage.COMPLETED.value
    job.progress = 100
    job.completed_at = datetime.now(timezone.utc)
    if originality_report["blocked"] or policy_payload.get("blocked"):
        asset_group.status = GeneratedAssetGroupStatus.REJECTED.value
        cluster.workflow_state = TrendWorkflowState.ASSET_GENERATION.value
    else:
        asset_group.status = GeneratedAssetGroupStatus.REVIEWED.value
        cluster.workflow_state = TrendWorkflowState.ASSET_REVIEW.value
    await svc.audit.record(
        tenant_id=tenant_id,
        actor_user_id=None,
        action="content.generated",
        entity_type="generated_asset_group",
        entity_id=str(asset_group.id),
        message="Content generation job completed",
        payload={"content_plan_id": str(plan.id), "content_job_id": str(job.id)},
        payload_schema="generated_asset_group.v1",
        outcome="completed",
    )
    await svc.db.flush()
    return job
