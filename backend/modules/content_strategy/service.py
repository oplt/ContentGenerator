from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_strategy.models import Brand, BrandProfile, ContentFormat, ContentPlan, ContentPlanStatus
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.content_strategy.schemas import BrandProfileUpsertRequest, ContentPlanResponse
from backend.modules.story_intelligence.models import StoryCluster
from backend.modules.inference.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class ContentStrategyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContentStrategyRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)
        self.llm = get_llm_provider()

    async def get_or_create_brand_profile(self, tenant_id: UUID) -> BrandProfile:
        existing = await self.repo.get_brand_profile(tenant_id)
        if existing:
            if existing.brand_id is None:
                brand = await self._get_or_create_brand(tenant_id, existing)
                existing.brand_id = brand.id
                await self.db.flush()
            return existing
        brand = await self._get_or_create_brand(tenant_id)
        profile = BrandProfile(
            tenant_id=tenant_id,
            brand_id=brand.id,
            name="Default Brand",
            niche="general",
            tone="authoritative",
            audience="Busy social media audience looking for concise updates",
            preferred_platforms=["x", "bluesky", "instagram", "tiktok", "youtube"],
            default_cta="Follow for more timely updates.",
            hashtags_strategy="balanced",
            risk_tolerance="medium",
            require_whatsapp_approval=True,
            guardrails={"factuality": "Only use sourced claims"},
            visual_style={"palette": "slate and cyan"},
        )
        return await self.repo.create_brand_profile(profile)

    async def _get_or_create_brand(
        self,
        tenant_id: UUID,
        profile: BrandProfile | None = None,
    ) -> Brand:
        existing = await self.repo.get_brand(tenant_id)
        if existing:
            return existing
        seed_name = profile.name if profile else "Default Brand"
        seed_niche = profile.niche if profile else "general"
        seed_platforms = profile.preferred_platforms if profile else ["x", "bluesky", "instagram", "tiktok", "youtube"]
        brand = Brand(
            tenant_id=tenant_id,
            name=seed_name,
            niche=seed_niche,
            style_guide={
                "tone": profile.tone if profile else "authoritative",
                "audience": profile.audience if profile else "Busy social media audience looking for concise updates",
                "voice_notes": profile.voice_notes if profile else "",
                "visual_style": profile.visual_style if profile else {"palette": "slate and cyan"},
            },
            allowed_topics=[],
            blocked_topics=[],
            target_platforms=seed_platforms,
            risk_policy={
                "risk_tolerance": profile.risk_tolerance if profile else "medium",
                "guardrails": profile.guardrails if profile else {"factuality": "Only use sourced claims"},
            },
            posting_policy={
                "default_cta": profile.default_cta if profile else "Follow for more timely updates.",
                "hashtags_strategy": profile.hashtags_strategy if profile else "balanced",
                "approval_channel": "telegram",
            },
        )
        return await self.repo.create_brand(brand)

    async def upsert_brand_profile(
        self, tenant_id: UUID, payload: BrandProfileUpsertRequest
    ) -> BrandProfile:
        profile = await self.repo.get_brand_profile(tenant_id)
        brand = await self._get_or_create_brand(tenant_id, profile)
        if profile:
            for key, value in payload.model_dump().items():
                setattr(profile, key, value)
            profile.brand_id = brand.id
            brand.name = profile.name
            brand.niche = profile.niche
            brand.style_guide = {
                **brand.style_guide,
                "tone": profile.tone,
                "audience": profile.audience,
                "voice_notes": profile.voice_notes or "",
                "visual_style": profile.visual_style,
            }
            brand.target_platforms = profile.preferred_platforms
            brand.risk_policy = {
                "risk_tolerance": profile.risk_tolerance,
                "guardrails": profile.guardrails,
            }
            brand.posting_policy = {
                "default_cta": profile.default_cta,
                "hashtags_strategy": profile.hashtags_strategy,
                "approval_channel": "telegram",
            }
            await self.db.flush()
            return profile
        brand.name = payload.name
        brand.niche = payload.niche
        brand.style_guide = {
            **brand.style_guide,
            "tone": payload.tone,
            "audience": payload.audience,
            "voice_notes": payload.voice_notes or "",
            "visual_style": payload.visual_style,
        }
        brand.target_platforms = payload.preferred_platforms
        brand.risk_policy = {
            "risk_tolerance": payload.risk_tolerance,
            "guardrails": payload.guardrails,
        }
        brand.posting_policy = {
            "default_cta": payload.default_cta,
            "hashtags_strategy": payload.hashtags_strategy,
            "approval_channel": "telegram",
        }
        await self.db.flush()
        return await self.repo.create_brand_profile(
            BrandProfile(tenant_id=tenant_id, brand_id=brand.id, **payload.model_dump())
        )

    async def list_content_plans(self, tenant_id: UUID) -> list[ContentPlan]:
        return await self.repo.list_content_plans(tenant_id)

    async def get_content_plan(self, tenant_id: UUID, plan_id: UUID) -> ContentPlan:
        plan = await self.repo.get_content_plan(tenant_id, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        return plan

    async def create_plan_for_cluster(
        self,
        *,
        tenant_id: UUID,
        cluster_id: UUID,
        brand_profile_id: UUID | None = None,
    ) -> ContentPlan:
        existing = await self.repo.get_plan_for_cluster(tenant_id, cluster_id)
        if existing:
            return existing
        cluster = await self.story_repo.get_cluster(tenant_id, cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")
        brand_profile = await self.repo.get_brand_profile(tenant_id)
        if brand_profile_id and brand_profile and brand_profile.id != brand_profile_id:
            brand_profile = brand_profile
        if not brand_profile:
            brand_profile = await self.get_or_create_brand_profile(tenant_id)

        score = float(cluster.explainability.get("score", "0.0"))
        content_format = (
            ContentFormat.BOTH.value
            if score >= 0.75
            else ContentFormat.TEXT.value if score < 0.62 else ContentFormat.VIDEO.value
        )
        target_platforms = brand_profile.preferred_platforms
        if content_format == ContentFormat.TEXT.value:
            target_platforms = [platform for platform in target_platforms if platform in {"x", "bluesky", "instagram"}]
        elif content_format == ContentFormat.VIDEO.value:
            target_platforms = [platform for platform in target_platforms if platform in {"youtube", "instagram", "tiktok"}]
        unsafe = cluster.risk_level == "unsafe"
        policy_trace = {
            "cluster_score": f"{score:.2f}",
            "risk_level": cluster.risk_level,
            "topic": cluster.primary_topic,
        }
        refinement = await self.llm.summarize(
            f"Topic: {cluster.primary_topic}\nHeadline: {cluster.headline}\nSummary: {cluster.summary}",
            max_words=35,
        )
        plan = ContentPlan(
            tenant_id=tenant_id,
            story_cluster_id=cluster.id,
            brand_profile_id=brand_profile.id,
            status=ContentPlanStatus.READY.value,
            decision="generate" if cluster.worthy_for_content and not unsafe else "hold",
            content_format=content_format,
            target_platforms=target_platforms,
            tone=brand_profile.tone,
            urgency="breaking" if score >= 0.8 else "normal",
            risk_flags=[cluster.risk_level] if cluster.risk_level != "safe" else [],
            recommended_cta=brand_profile.default_cta,
            hashtags_strategy=brand_profile.hashtags_strategy,
            approval_required=brand_profile.require_whatsapp_approval,
            safe_to_publish=not unsafe,
            policy_trace={**policy_trace, "llm_refinement": refinement},
        )
        plan = await self.repo.create_content_plan(plan)
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="content.plan_created",
            entity_type="content_plan",
            entity_id=str(plan.id),
            message="Content plan created from story cluster",
            payload={"story_cluster_id": str(cluster.id), "decision": plan.decision},
        )
        await self.db.flush()
        return plan
