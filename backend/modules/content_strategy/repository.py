from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import redis_cache
from backend.modules.content_strategy.models import Brand, BrandProfile, ContentPlan


class ContentStrategyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_brand(self, tenant_id: UUID) -> Brand | None:
        # Try to get from cache first
        cache_key = f"brand:{tenant_id}"
        cached_brand = await redis_cache.get(cache_key)
        if cached_brand is not None:
            return Brand(**cached_brand)

        # If not in cache, get from database
        result = await self.db.execute(
            select(Brand)
            .where(Brand.tenant_id == tenant_id, Brand.deleted_at.is_(None))
            .order_by(Brand.created_at.asc())
            .limit(1)
        )
        brand = result.scalar_one_or_none()
        
        # Cache the result if found
        if brand:
            await redis_cache.set(cache_key, brand.model_dump(), expire=3600)  # Cache for 1 hour
        
        return brand

    async def create_brand(self, brand: Brand) -> Brand:
        self.db.add(brand)
        await self.db.flush()
        
        # Invalidate cache for this tenant's brand
        cache_key = f"brand:{brand.tenant_id}"
        await redis_cache.delete(cache_key)
        
        return brand

    async def get_brand_profile(self, tenant_id: UUID) -> BrandProfile | None:
        # Try to get from cache first
        cache_key = f"brand_profile:{tenant_id}"
        cached_profile = await redis_cache.get(cache_key)
        if cached_profile is not None:
            return BrandProfile(**cached_profile)

        # If not in cache, get from database
        result = await self.db.execute(
            select(BrandProfile)
            .where(BrandProfile.tenant_id == tenant_id, BrandProfile.deleted_at.is_(None))
            .order_by(BrandProfile.created_at.asc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()
        
        # Cache the result if found
        if profile:
            await redis_cache.set(cache_key, profile.model_dump(), expire=3600)  # Cache for 1 hour
        
        return profile

    async def get_brand_profile_by_id(self, tenant_id: UUID, profile_id: UUID) -> BrandProfile | None:
        # Try to get from cache first
        cache_key = f"brand_profile_by_id:{profile_id}"
        cached_profile = await redis_cache.get(cache_key)
        if cached_profile is not None:
            return BrandProfile(**cached_profile)

        # If not in cache, get from database
        result = await self.db.execute(
            select(BrandProfile).where(
                BrandProfile.tenant_id == tenant_id,
                BrandProfile.id == profile_id,
                BrandProfile.deleted_at.is_(None),
            )
        )
        profile = result.scalar_one_or_none()
        
        # Cache the result if found
        if profile:
            await redis_cache.set(cache_key, profile.model_dump(), expire=3600)  # Cache for 1 hour
        
        return profile

    async def create_brand_profile(self, profile: BrandProfile) -> BrandProfile:
        self.db.add(profile)
        await self.db.flush()
        
        # Invalidate cache for this tenant's brand profile
        cache_key = f"brand_profile:{profile.tenant_id}"
        await redis_cache.delete(cache_key)
        
        # Invalidate cache for this specific profile
        cache_key_by_id = f"brand_profile_by_id:{profile.id}"
        await redis_cache.delete(cache_key_by_id)
        
        return profile

    async def list_content_plans(self, tenant_id: UUID, limit: int = 50) -> list[ContentPlan]:
        # Try to get from cache first
        cache_key = f"content_plans:{tenant_id}:{limit}"
        cached_plans = await redis_cache.get(cache_key)
        if cached_plans is not None:
            return [ContentPlan(**plan) for plan in cached_plans]

        # If not in cache, get from database
        result = await self.db.execute(
            select(ContentPlan)
            .where(ContentPlan.tenant_id == tenant_id, ContentPlan.deleted_at.is_(None))
            .order_by(ContentPlan.created_at.desc())
            .limit(limit)
        )
        plans = list(result.scalars().all())
        
        # Cache the result
        if plans:
            await redis_cache.set(cache_key, [plan.model_dump() for plan in plans], expire=1800)  # Cache for 30 minutes
        
        return plans

    async def get_content_plan(self, tenant_id: UUID, plan_id: UUID) -> ContentPlan | None:
        # Try to get from cache first
        cache_key = f"content_plan:{plan_id}"
        cached_plan = await redis_cache.get(cache_key)
        if cached_plan is not None:
            return ContentPlan(**cached_plan)

        # If not in cache, get from database
        result = await self.db.execute(
            select(ContentPlan).where(
                ContentPlan.id == plan_id,
                ContentPlan.tenant_id == tenant_id,
                ContentPlan.deleted_at.is_(None),
            )
        )
        plan = result.scalar_one_or_none()
        
        # Cache the result if found
        if plan:
            await redis_cache.set(cache_key, plan.model_dump(), expire=1800)  # Cache for 30 minutes
        
        return plan

    async def get_plan_for_cluster(self, tenant_id: UUID, cluster_id: UUID) -> ContentPlan | None:
        # Try to get from cache first
        cache_key = f"plan_for_cluster:{cluster_id}"
        cached_plan = await redis_cache.get(cache_key)
        if cached_plan is not None:
            return ContentPlan(**cached_plan)

        # If not in cache, get from database
        result = await self.db.execute(
            select(ContentPlan)
            .where(
                ContentPlan.tenant_id == tenant_id,
                ContentPlan.story_cluster_id == cluster_id,
                ContentPlan.deleted_at.is_(None),
            )
            .order_by(ContentPlan.created_at.desc())
            .limit(1)
        )
        plan = result.scalar_one_or_none()
        
        # Cache the result if found
        if plan:
            await redis_cache.set(cache_key, plan.model_dump(), expire=1800)  # Cache for 30 minutes
        
        return plan

    async def create_content_plan(self, plan: ContentPlan) -> ContentPlan:
        self.db.add(plan)
        await self.db.flush()
        
        # Invalidate cache for tenant's content plans
        cache_key_plans = f"content_plans:{plan.tenant_id}:50"
        await redis_cache.delete(cache_key_plans)
        
        # Invalidate cache for cluster's plan
        cache_key_cluster = f"plan_for_cluster:{plan.story_cluster_id}"
        await redis_cache.delete(cache_key_cluster)
        
        # Invalidate cache for specific plan
        cache_key_plan = f"content_plan:{plan.id}"
        await redis_cache.delete(cache_key_plan)
        
        return plan
