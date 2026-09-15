from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.tenant_cache import (
    OWNER_CONTENT_STRATEGY,
    CachePolicy,
    build_cache_key,
    hydrate_orm,
    orm_column_dict,
    tenant_cache,
)
from backend.modules.content_strategy.models import Brand, BrandProfile, ContentPlan

_POLICY = CachePolicy(owner=OWNER_CONTENT_STRATEGY, ttl_seconds=3600, negative_ttl_seconds=30)
_LIST_POLICY = CachePolicy(owner=OWNER_CONTENT_STRATEGY, ttl_seconds=1800, negative_ttl_seconds=0)


class ContentStrategyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_brand(self, tenant_id: UUID) -> Brand | None:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity="brand:default",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(Brand)
                .where(Brand.tenant_id == tenant_id, Brand.deleted_at.is_(None))
                .order_by(Brand.created_at.asc())
                .limit(1)
            )
            brand = result.scalar_one_or_none()
            return orm_column_dict(brand) if brand else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_POLICY,
            factory=_load,
            legacy_keys=[f"brand:{tenant_id}"],
        )
        return hydrate_orm(Brand, payload) if payload else None

    async def create_brand(self, brand: Brand) -> Brand:
        self.db.add(brand)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=brand.tenant_id,
                identity="brand:default",
            ),
            f"brand:{brand.tenant_id}",
        )
        return brand

    async def get_brand_profile(self, tenant_id: UUID) -> BrandProfile | None:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity="brand_profile:default",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(BrandProfile)
                .where(BrandProfile.tenant_id == tenant_id, BrandProfile.deleted_at.is_(None))
                .order_by(BrandProfile.created_at.asc())
                .limit(1)
            )
            profile = result.scalar_one_or_none()
            return orm_column_dict(profile) if profile else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_POLICY,
            factory=_load,
            legacy_keys=[f"brand_profile:{tenant_id}"],
        )
        return hydrate_orm(BrandProfile, payload) if payload else None

    async def get_brand_profile_by_id(self, tenant_id: UUID, profile_id: UUID) -> BrandProfile | None:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity=f"brand_profile:{profile_id}",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(BrandProfile).where(
                    BrandProfile.tenant_id == tenant_id,
                    BrandProfile.id == profile_id,
                    BrandProfile.deleted_at.is_(None),
                )
            )
            profile = result.scalar_one_or_none()
            return orm_column_dict(profile) if profile else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_POLICY,
            factory=_load,
            legacy_keys=[f"brand_profile_by_id:{profile_id}"],
        )
        return hydrate_orm(BrandProfile, payload) if payload else None

    async def create_brand_profile(self, profile: BrandProfile) -> BrandProfile:
        self.db.add(profile)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=profile.tenant_id,
                identity="brand_profile:default",
            ),
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=profile.tenant_id,
                identity=f"brand_profile:{profile.id}",
            ),
            f"brand_profile:{profile.tenant_id}",
            f"brand_profile_by_id:{profile.id}",
        )
        return profile

    async def list_content_plans(self, tenant_id: UUID, limit: int = 50) -> list[ContentPlan]:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity=f"content_plans:{limit}",
        )

        async def _load() -> list[dict] | None:
            result = await self.db.execute(
                select(ContentPlan)
                .where(ContentPlan.tenant_id == tenant_id, ContentPlan.deleted_at.is_(None))
                .order_by(ContentPlan.created_at.desc())
                .limit(limit)
            )
            plans = list(result.scalars().all())
            return [orm_column_dict(plan) for plan in plans] if plans else []

        payload = await tenant_cache.get_or_set(
            key,
            policy=_LIST_POLICY,
            factory=_load,
            legacy_keys=[f"content_plans:{tenant_id}:{limit}"],
        )
        if not payload:
            return []
        return [hydrate_orm(ContentPlan, item) for item in payload]

    async def get_content_plan(self, tenant_id: UUID, plan_id: UUID) -> ContentPlan | None:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity=f"content_plan:{plan_id}",
        )

        async def _load() -> dict | None:
            result = await self.db.execute(
                select(ContentPlan).where(
                    ContentPlan.id == plan_id,
                    ContentPlan.tenant_id == tenant_id,
                    ContentPlan.deleted_at.is_(None),
                )
            )
            plan = result.scalar_one_or_none()
            return orm_column_dict(plan) if plan else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_LIST_POLICY,
            factory=_load,
            legacy_keys=[f"content_plan:{plan_id}"],
        )
        return hydrate_orm(ContentPlan, payload) if payload else None

    async def get_plan_for_cluster(self, tenant_id: UUID, cluster_id: UUID) -> ContentPlan | None:
        key = build_cache_key(
            owner=OWNER_CONTENT_STRATEGY,
            tenant_id=tenant_id,
            identity=f"plan_for_cluster:{cluster_id}",
        )

        async def _load() -> dict | None:
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
            return orm_column_dict(plan) if plan else None

        payload = await tenant_cache.get_or_set(
            key,
            policy=_LIST_POLICY,
            factory=_load,
            legacy_keys=[f"plan_for_cluster:{cluster_id}"],
        )
        return hydrate_orm(ContentPlan, payload) if payload else None

    async def create_content_plan(self, plan: ContentPlan) -> ContentPlan:
        self.db.add(plan)
        await self.db.flush()
        await tenant_cache.delete(
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=plan.tenant_id,
                identity="content_plans:50",
            ),
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=plan.tenant_id,
                identity=f"plan_for_cluster:{plan.story_cluster_id}",
            ),
            build_cache_key(
                owner=OWNER_CONTENT_STRATEGY,
                tenant_id=plan.tenant_id,
                identity=f"content_plan:{plan.id}",
            ),
            f"content_plans:{plan.tenant_id}:50",
            f"plan_for_cluster:{plan.story_cluster_id}",
            f"content_plan:{plan.id}",
        )
        return plan
