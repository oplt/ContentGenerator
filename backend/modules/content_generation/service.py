from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_generation.asset_persistence import AssetPersistenceMixin
from backend.modules.content_generation.asset_specs import build_platform_asset_specs
from backend.modules.content_generation.brand_voice import BrandVoiceMixin
from backend.modules.content_generation.generation_context import PLATFORM_LIMITS, GenerationContextMixin
from backend.modules.content_generation.models import ContentJob, GeneratedAsset, GeneratedAssetGroup
from backend.modules.content_generation.originality import OriginalityMixin
from backend.modules.content_generation.quality import QualityMixin
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.revisions import (
    regenerate_asset_group as regenerate_asset_group_helper,
    regenerate_with_feedback as regenerate_with_feedback_helper,
)
from backend.modules.content_generation.schemas import ContentJobResponse, GeneratedAssetResponse
from backend.modules.content_generation.workflow import generate_content as generate_content_helper
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.inference.providers import get_llm_provider
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.video_pipeline.service import VideoPipelineService

__all__ = ["ContentGenerationService", "PLATFORM_LIMITS"]


class ContentGenerationService(
    GenerationContextMixin,
    QualityMixin,
    OriginalityMixin,
    BrandVoiceMixin,
    AssetPersistenceMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContentGenerationRepository(db)
        self.plan_repo = ContentStrategyRepository(db)
        self.publishing_repo = PublishingRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)
        self.video_pipeline = VideoPipelineService(db)
        self.llm = get_llm_provider()
        self.fact_review = FactRiskReviewService()

    def _build_platform_asset_specs(
        self,
        *,
        cluster: StoryCluster,
        brief: Any,
        plan: Any,
        profile: Any,
        orch_result: Any,
        effective_platforms: list[str],
        primary_platform: str,
        source_articles: list[NormalizedArticle],
    ) -> list[dict[str, Any]]:
        return build_platform_asset_specs(
            self,
            cluster=cluster,
            brief=brief,
            plan=plan,
            profile=profile,
            orch_result=orch_result,
            effective_platforms=effective_platforms,
            primary_platform=primary_platform,
            source_articles=source_articles,
        )

    async def generate(
        self,
        *,
        tenant_id: UUID,
        plan_id: UUID,
        feedback: str | None = None,
        revision_of_job_id: UUID | None = None,
        social_account_ids: list[UUID] | None = None,
    ) -> ContentJob:
        return await generate_content_helper(
            self,
            tenant_id=tenant_id,
            plan_id=plan_id,
            feedback=feedback,
            revision_of_job_id=revision_of_job_id,
            social_account_ids=social_account_ids,
        )

    async def regenerate_with_feedback(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        feedback: str,
        requested_by_user_id: UUID | None,
        source_channel: str,
    ) -> ContentJob:
        return await regenerate_with_feedback_helper(
            self,
            tenant_id=tenant_id,
            job_id=job_id,
            feedback=feedback,
            requested_by_user_id=requested_by_user_id,
            source_channel=source_channel,
        )

    async def regenerate_asset_group(
        self,
        *,
        tenant_id: UUID,
        asset_group_id: UUID,
        instruction: str,
        requested_by_user_id: UUID | None,
        source_channel: str,
    ) -> ContentJob:
        return await regenerate_asset_group_helper(
            self,
            tenant_id=tenant_id,
            asset_group_id=asset_group_id,
            instruction=instruction,
            requested_by_user_id=requested_by_user_id,
            source_channel=source_channel,
        )

    async def list_jobs(self, tenant_id: UUID) -> list[ContentJob]:
        return await self.repo.list_jobs(tenant_id)

    async def list_job_details(self, tenant_id: UUID) -> list[ContentJobResponse]:
        jobs = await self.repo.list_jobs(tenant_id)
        job_ids = [job.id for job in jobs]
        assets_by_job = await self.repo.list_assets_for_jobs(job_ids)
        groups_by_job = await self.repo.list_asset_groups_for_jobs(job_ids)
        return [
            self._build_job_response(
                job,
                assets_by_job.get(job.id, []),
                groups_by_job.get(job.id),
            )
            for job in jobs
        ]

    @staticmethod
    def _build_job_response(
        job: ContentJob,
        assets: list[GeneratedAsset],
        asset_group: GeneratedAssetGroup | None = None,
    ) -> ContentJobResponse:
        asset_group_id = next(
            (asset.asset_group_id for asset in assets if asset.asset_group_id),
            asset_group.id if asset_group else None,
        )
        return ContentJobResponse(
            id=job.id,
            content_plan_id=job.content_plan_id,
            revision_of_job_id=job.revision_of_job_id,
            job_type=str(job.job_type),
            status=str(job.status),
            stage=str(job.stage),
            progress=job.progress,
            feedback=job.feedback,
            error_message=job.error_message,
            risk_label=cast(str | None, job.grounding_bundle.get("risk_label")),
            risk_review=cast(dict[str, object], job.grounding_bundle.get("risk_review", {})),
            target_social_account_ids=list(getattr(job, "target_social_account_ids", None) or []),
            variant_fingerprints=cast(
                dict[str, list[str]],
                job.grounding_bundle.get("variant_fingerprints", {}) or {},
            ),
            asset_group_id=asset_group_id,
            started_at=job.started_at,
            completed_at=job.completed_at,
            assets=[
                GeneratedAssetResponse(
                    id=asset.id,
                    asset_type=str(asset.asset_type),
                    platform=asset.platform,
                    variant_label=asset.variant_label,
                    public_url=asset.public_url,
                    mime_type=asset.mime_type,
                    metadata=asset.asset_metadata,
                    source_trace=asset.source_trace,
                    text_content=asset.text_content,
                    asset_group_id=asset.asset_group_id,
                )
                for asset in assets
            ],
        )

    async def get_job_detail(self, tenant_id: UUID, job_id: UUID) -> ContentJobResponse:
        job = await self.repo.get_job(tenant_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.repo.list_assets(job.id)
        asset_group = None
        if not any(asset.asset_group_id for asset in assets):
            group = await self.repo.get_asset_group_for_job(job.id)
            asset_group = group
        return self._build_job_response(job, assets, asset_group)
