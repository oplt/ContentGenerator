from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_generation.models import (
    ContentJob,
    ContentJobStatus,
    ContentJobType,
    ContentRevision,
    GeneratedAsset,
    GeneratedAssetType,
    VideoStage,
)
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.schemas import ContentJobResponse, GeneratedAssetResponse
from backend.modules.content_strategy.models import ContentFormat
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster
from backend.modules.story_intelligence.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.video_pipeline.service import VideoPipelineService


PLATFORM_LIMITS = {
    "x": 280,
    "bluesky": 300,
    "instagram": 1000,
    "tiktok": 400,
    "youtube_title": 95,
    "youtube_description": 1000,
}


class ContentGenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContentGenerationRepository(db)
        self.plan_repo = ContentStrategyRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)
        self.video_pipeline = VideoPipelineService(db)
        self.llm = get_llm_provider()

    def _prompt_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "prompts" / "text_generation" / "v1"

    def _load_template(self, name: str) -> str:
        template_path = self._prompt_dir() / f"{name}.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return "Write grounded platform content from the supplied facts."

    def _trim(self, text: str, limit: int) -> str:
        return text[: limit - 3] + "..." if len(text) > limit else text

    def _build_hashtags(self, topic: str, strategy: str) -> str:
        base = [f"#{topic.replace(' ', '')}"]
        if strategy == "aggressive":
            base.extend(["#TrendingNow", "#BreakingNews"])
        return " ".join(base[:3])

    def _grounding_block(
        self,
        cluster: StoryCluster,
        source_articles: list[NormalizedArticle],
        feedback: str | None,
    ) -> str:
        article_snippets = "\n".join(
            f"- [{a.source_name}] {a.title}: {(a.summary or a.body or '')[:300]}"
            for a in source_articles[:3]
        )
        feedback_note = f"\nRevision instruction: {feedback}" if feedback else ""
        return (
            f"VERIFIED FACTS (use only these, do not add claims not present here):\n"
            f"Headline: {cluster.headline}\n"
            f"Summary: {cluster.summary}\n"
            f"Key entities: {cluster.explainability.get('keywords', cluster.primary_topic)}\n"
            f"Source articles:\n{article_snippets}"
            f"{feedback_note}"
        )

    def _hallucination_guard(self, text: str, entities: list[str]) -> bool:
        """Return True if at least half of the key entities appear in the generated text."""
        if not entities:
            return True
        text_lower = text.lower()
        matches = sum(1 for e in entities if e.lower() in text_lower)
        return matches >= max(1, len(entities) // 2)

    async def _draft_platform_variants(
        self,
        *,
        platform: str,
        cluster: StoryCluster,
        tone: str,
        cta: str | None,
        hashtags_strategy: str,
        source_articles: list[NormalizedArticle],
        feedback: str | None = None,
    ) -> list[tuple[str, str]]:
        hashtags = self._build_hashtags(cluster.primary_topic, hashtags_strategy)
        limit = PLATFORM_LIMITS.get("youtube_description" if platform == "youtube" else platform, 280)
        grounding = self._grounding_block(cluster, source_articles, feedback)
        template = self._load_template(platform)

        if platform == "youtube":
            title_prompt = (
                f"{grounding}\n\n"
                f"Write a YouTube video title (max {PLATFORM_LIMITS['youtube_title']} chars). "
                f"Tone: {tone}. Be accurate, not clickbait."
            )
            desc_prompt = (
                f"{grounding}\n\n"
                f"Write a YouTube video description (max {PLATFORM_LIMITS['youtube_description']} chars). "
                f"Tone: {tone}. Include {cta or 'Subscribe for more'}. "
                f"End with: 'Sources available on request.'"
            )
            title = self._trim(await self.llm.generate(title_prompt, max_tokens=50, temperature=0.5), PLATFORM_LIMITS["youtube_title"])
            description = self._trim(await self.llm.generate(desc_prompt, max_tokens=400, temperature=0.6), PLATFORM_LIMITS["youtube_description"])
            return [("title", title), ("description", description)]

        prompt = (
            f"{template}\n\n"
            f"{grounding}\n\n"
            f"Platform: {platform} (max {limit} characters per variant)\n"
            f"Tone: {tone}\n"
            f"CTA: {cta or 'Follow for more'}\n"
            f"Hashtags to include: {hashtags}\n\n"
            f"Write exactly 3 variants labeled A, B, C. "
            f"Each variant must stand alone and fit within {limit} characters. "
            f"Only use facts from the VERIFIED FACTS block above."
        )
        response = await self.llm.generate(prompt, max_tokens=600, temperature=0.7)

        # Parse A/B/C from the response; fall back to slicing if format is off
        variants = self._parse_abc_variants(response, cluster, hashtags, cta, limit)
        entities = cluster.explainability.get("keywords", "").split(", ")[:4]
        validated = []
        for label, content in variants:
            if self._hallucination_guard(content, entities):
                validated.append((label, self._trim(content, limit)))
            else:
                # Entity check failed — fall back to template-safe variant
                safe = self._trim(f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip(), limit)
                validated.append((label, safe))
        return validated

    def _parse_abc_variants(
        self,
        response: str,
        cluster: StoryCluster,
        hashtags: str,
        cta: str | None,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Extract A/B/C variants from LLM response. Falls back to template on parse failure."""
        import re
        parts: dict[str, str] = {}
        for match in re.finditer(r"(?:^|\n)\s*([ABC])[):.]\s*(.+?)(?=\n\s*[ABC][):.]|\Z)", response, re.DOTALL):
            label, text = match.group(1), match.group(2).strip()
            parts[label] = text
        if len(parts) >= 2:
            return [(label, parts[label]) for label in ("A", "B", "C") if label in parts]
        # Fallback templates
        base = f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip()
        return [
            ("A", base),
            ("B", f"{cluster.headline}\n{cluster.summary}\n{cta or 'Follow for more.'} {hashtags}"),
            ("C", f"{cluster.primary_topic.title()} update: {cluster.summary} {hashtags}"),
        ]

    async def _create_asset(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        asset_type: GeneratedAssetType,
        platform: str | None,
        variant_label: str | None,
        text_content: str,
        source_trace: dict[str, str],
    ) -> GeneratedAsset:
        asset = GeneratedAsset(
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            asset_type=asset_type.value,
            platform=platform,
            variant_label=variant_label,
            mime_type="text/markdown",
            text_content=text_content,
            asset_metadata={"template_version": "v1"},
            source_trace=source_trace,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def generate(self, *, tenant_id: UUID, plan_id: UUID, feedback: str | None = None, revision_of_job_id: UUID | None = None) -> ContentJob:
        plan = await self.plan_repo.get_content_plan(tenant_id, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        if plan.decision != "generate":
            raise HTTPException(status_code=400, detail="Content plan is not approved for generation")
        cluster = await self.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")

        job = await self.repo.create_job(
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
                },
                started_at=datetime.now(timezone.utc),
            )
        )

        # Fetch source articles for grounding
        source_articles = await self.story_repo.list_normalized_for_cluster(cluster.id)

        source_trace = {
            "story_cluster_id": str(cluster.id),
            "headline": cluster.headline,
            "keywords": cluster.explainability.get("keywords", ""),
            "source_article_count": str(len(source_articles)),
        }
        for platform in plan.target_platforms:
            variants = await self._draft_platform_variants(
                platform=platform,
                cluster=cluster,
                tone=plan.tone,
                cta=plan.recommended_cta,
                hashtags_strategy=plan.hashtags_strategy,
                source_articles=source_articles,
                feedback=feedback,
            )
            for label, content in variants:
                await self._create_asset(
                    tenant_id=tenant_id,
                    content_job_id=job.id,
                    asset_type=GeneratedAssetType.TEXT_VARIANT,
                    platform=platform,
                    variant_label=label,
                    text_content=content,
                    source_trace=source_trace,
                )

        if plan.content_format in {ContentFormat.VIDEO.value, ContentFormat.BOTH.value}:
            job.stage = VideoStage.RESEARCHING.value
            job.progress = 35
            await self.video_pipeline.run(job=job, cluster=cluster)

        job.status = ContentJobStatus.COMPLETED.value
        job.stage = VideoStage.COMPLETED.value
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="content.generated",
            entity_type="content_job",
            entity_id=str(job.id),
            message="Content generation job completed",
            payload={"content_plan_id": str(plan.id)},
        )
        await self.db.flush()
        return job

    async def regenerate_with_feedback(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        feedback: str,
        requested_by_user_id: UUID | None,
        source_channel: str,
    ) -> ContentJob:
        original_job = await self.repo.get_job(tenant_id, job_id)
        if not original_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        latest_revision_number = 1
        await self.repo.create_revision(
            ContentRevision(
                tenant_id=tenant_id,
                content_job_id=original_job.id,
                revision_number=latest_revision_number,
                feedback=feedback,
                source_channel=source_channel,
                requested_by_user_id=requested_by_user_id,
                status="processing",
                diff_summary="Regenerated copy using provided feedback",
                revision_payload={"feedback": feedback},
            )
        )
        return await self.generate(
            tenant_id=tenant_id,
            plan_id=original_job.content_plan_id,
            feedback=feedback,
            revision_of_job_id=original_job.id,
        )

    async def list_jobs(self, tenant_id: UUID) -> list[ContentJob]:
        return await self.repo.list_jobs(tenant_id)

    async def get_job_detail(self, tenant_id: UUID, job_id: UUID) -> ContentJobResponse:
        job = await self.repo.get_job(tenant_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.repo.list_assets(job.id)
        return ContentJobResponse(
            **{
                "id": job.id,
                "content_plan_id": job.content_plan_id,
                "revision_of_job_id": job.revision_of_job_id,
                "job_type": str(job.job_type),
                "status": str(job.status),
                "stage": str(job.stage),
                "progress": job.progress,
                "feedback": job.feedback,
                "error_message": job.error_message,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "assets": [
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
                    )
                    for asset in assets
                ],
            }
        )
