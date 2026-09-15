from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_generation.asset_persistence import persist_orchestrated_assets
from backend.modules.content_generation.workflow_finalize import _finalize_generation
from backend.modules.content_generation.workflow_stages import generation_stage
from backend.modules.content_generation.models import (
    ContentJob,
    ContentJobStatus,
    ContentJobType,
    GeneratedAsset,
    GeneratedAssetGroup,
    GeneratedAssetGroupStatus,
    VideoStage,
)
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.editorial_briefs.models import BriefStatus
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.inference.orchestrator import ContentOrchestrator
from backend.modules.publishing.account_selection import (
    group_by_fingerprint,
    resolve_social_accounts,
    unique_platforms,
)
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.video_pipeline.service import VideoPipelineService


class _WorkflowDeps(Protocol):
    db: AsyncSession
    repo: ContentGenerationRepository
    plan_repo: ContentStrategyRepository
    publishing_repo: PublishingRepository
    story_repo: StoryIntelligenceRepository
    audit: AuditService
    video_pipeline: VideoPipelineService
    llm: Any

    def _build_platform_asset_specs(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    async def _create_assets_batch(self, specs: list[dict[str, Any]]) -> list[GeneratedAsset]: ...


async def generate_content(
    svc: _WorkflowDeps,
    *,
    tenant_id: UUID,
    plan_id: UUID,
    feedback: str | None = None,
    revision_of_job_id: UUID | None = None,
    social_account_ids: list[UUID] | None = None,
) -> ContentJob:
    plan = await svc.plan_repo.get_content_plan(tenant_id, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Content plan not found")
    if plan.decision != "generate":
        raise HTTPException(status_code=400, detail="Content plan is not approved for generation")
    cluster = await svc.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
    if not cluster:
        raise HTTPException(status_code=404, detail="Story cluster not found")

    # Gate: require an approved editorial brief before generating content
    brief_repo = EditorialBriefRepository(svc.db)
    brief = await brief_repo.get_by_cluster(tenant_id, plan.story_cluster_id)
    if not brief or brief.status != BriefStatus.APPROVED.value:
        raise HTTPException(
            status_code=422,
            detail=(
                "An approved editorial brief is required before generating content. "
                "Create and approve a brief for this story cluster first."
            ),
        )

    selected_accounts = await resolve_social_accounts(
        repo=svc.publishing_repo,
        tenant_id=tenant_id,
        social_account_ids=social_account_ids,
        stored_account_ids=getattr(plan, "target_social_account_ids", None) or [],
    )
    account_id_strs = [str(account.id) for account in selected_accounts]
    if social_account_ids:
        plan.target_social_account_ids = account_id_strs
    fingerprint_groups = group_by_fingerprint(selected_accounts)
    variant_fingerprints = {
        fingerprint: [str(account.id) for account in accounts]
        for fingerprint, accounts in fingerprint_groups.items()
    }
    # One LLM variant per unique platform fingerprint key (platform prefix).
    account_platforms = unique_platforms(selected_accounts)
    preferred_platforms = account_platforms or list(plan.target_platforms or [])

    with generation_stage("prepare", tenant_id=tenant_id):
        job = await svc.repo.create_job(
            ContentJob(
                tenant_id=tenant_id,
                content_plan_id=plan.id,
                revision_of_job_id=revision_of_job_id,
                job_type=ContentJobType.REVISION.value if feedback else plan.content_format,
                status=ContentJobStatus.RUNNING.value,
                stage=VideoStage.QUEUED.value,
                progress=5,
                feedback=feedback,
                grounding_bundle={
                    "headline": cluster.headline,
                    "summary": cluster.summary,
                    "topic": cluster.primary_topic,
                    "variant_fingerprints": variant_fingerprints,
                    "target_social_account_ids": account_id_strs,
                },
                target_social_account_ids=account_id_strs,
                started_at=datetime.now(timezone.utc),
            )
        )
        asset_group = await svc.repo.create_asset_group(
            GeneratedAssetGroup(
                tenant_id=tenant_id,
                content_job_id=job.id,
                content_plan_id=plan.id,
                status=GeneratedAssetGroupStatus.CREATED.value,
                platform_targets=preferred_platforms,
                target_social_account_ids=account_id_strs,
                asset_types=[],
                generation_trace={
                    "brief_id": str(brief.id),
                    "revision_of_job_id": str(revision_of_job_id) if revision_of_job_id else None,
                    "variant_fingerprints": variant_fingerprints,
                    "llm_platform_count": len(preferred_platforms),
                    "selected_account_count": len(selected_accounts),
                },
                quality_report={},
            )
        )
        cluster.workflow_state = TrendWorkflowState.ASSET_GENERATION.value
        job.stage = VideoStage.SCRIPTING.value
        job.progress = 15
        job.provider_metadata = {
            **(job.provider_metadata or {}),
            "pipeline_stage": "prepare",
            "stage_idempotency_key": f"content-job:{job.id}:prepare",
        }
        await svc.db.flush()
        # Split-phase: durable prepare before external LLM I/O.
        await svc.db.commit()

    with generation_stage("llm_generation", tenant_id=tenant_id, job_id=job.id):
        (
            orch_result,
            source_articles,
            effective_tone,
            profile,
            primary_platform,
        ) = await _run_llm_generation_stage(
            svc,
            tenant_id=tenant_id,
            job=job,
            plan=plan,
            cluster=cluster,
            brief=brief,
            preferred_platforms=preferred_platforms,
        )

    with generation_stage("asset_persist", job_id=job.id):
        (
            _asset_manifest,
            originality_report,
            _brand_voice_report,
            policy_payload,
            primary_platform,
            _effective_platforms,
        ) = await persist_orchestrated_assets(
            svc,
            tenant_id=tenant_id,
            job=job,
            asset_group=asset_group,
            cluster=cluster,
            brief=brief,
            plan=plan,
            profile=profile,
            orch_result=orch_result,
            preferred_platforms=preferred_platforms,
            source_articles=source_articles,
            effective_tone=effective_tone,
        )

    with generation_stage("finalize", job_id=job.id):
        return await _finalize_generation(
            svc,
            tenant_id=tenant_id,
            job=job,
            asset_group=asset_group,
            cluster=cluster,
            plan=plan,
            originality_report=originality_report,
            policy_payload=policy_payload,
            primary_platform=primary_platform,
        )


async def _run_llm_generation_stage(
    svc: _WorkflowDeps,
    *,
    tenant_id: UUID,
    job: ContentJob,
    plan: Any,
    cluster: Any,
    brief: Any,
    preferred_platforms: list[str],
) -> tuple[Any, list[Any], str, Any, str]:
    # Fetch source articles for grounding
    source_articles = await svc.story_repo.list_normalized_for_cluster(cluster.id)
    body_text = "\n".join((a.body or a.summary or "")[:600] for a in source_articles[:3])

    # ── Optimization-informed tone selection ─────────────────────────────
    primary_platform = preferred_platforms[0] if preferred_platforms else "x"
    effective_tone = plan.tone
    try:
        from backend.modules.analytics.optimization import OptimizationService

        opt_svc = OptimizationService(svc.db)
        recommended_tone = await opt_svc.best_tone_for_platform(tenant_id, primary_platform)
        if recommended_tone:
            effective_tone = recommended_tone
    except Exception:
        pass  # Fall back to plan tone if optimization data is unavailable

    profile = None
    if getattr(plan, "brand_profile_id", None):
        try:
            brand_profile_id = plan.brand_profile_id
            if brand_profile_id is not None:
                profile = await svc.plan_repo.get_brand_profile_by_id(tenant_id, brand_profile_id)
        except Exception:
            profile = None
    if not profile:
        try:
            profile = await svc.plan_repo.get_brand_profile(tenant_id)
        except Exception:
            profile = None

    # ── Multi-role orchestration pipeline (no durable writes mid-LLM) ───
    job.provider_metadata = {
        **(job.provider_metadata or {}),
        "pipeline_stage": "llm_generation",
        "stage_idempotency_key": f"content-job:{job.id}:llm_generation",
    }
    await svc.db.flush()
    orchestrator = ContentOrchestrator(llm=svc.llm)
    orch_result = await orchestrator.run(
        headline=cluster.headline,
        summary=cluster.summary or "",
        body=body_text,
        angle=brief.angle or "",
        talking_points=list(brief.talking_points or []),
        content_vertical=getattr(cluster, "content_vertical", None) or "general",
        risk_level=getattr(cluster, "risk_level", None) or "safe",
        tone=effective_tone,
        audience="Social media audience",
        preferred_platforms=preferred_platforms,
        hashtags_strategy=plan.hashtags_strategy or "balanced",
        cta=plan.recommended_cta or "",
        worthiness_threshold=0.35,
    )

    # ── High-risk reviewer enforcement ────────────────────────────────────
    cluster_risk = getattr(cluster, "risk_level", "safe") or "safe"
    if cluster_risk in ("risky", "high_risk") and not orch_result.reviewer.passed:
        if not orch_result.reviewer.revised_draft:
            job.status = ContentJobStatus.FAILED.value
            job.error_message = (
                "Content reviewer rejected draft for high-risk story: "
                + "; ".join(orch_result.reviewer.issues)
            )
            await svc.db.flush()
            raise HTTPException(
                status_code=422,
                detail=job.error_message,
            )

    return orch_result, source_articles, effective_tone, profile, primary_platform
