from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings

_WEAK_SECRETS = {"change-me", "secret", "changeme", "dev", ""}


def _assert_production_secrets() -> None:
    if settings.APP_ENV != "production":
        return
    if settings.JWT_SECRET in _WEAK_SECRETS:
        raise RuntimeError("JWT_SECRET must be set to a strong secret in production")
    if not settings.COOKIE_SECURE:
        raise RuntimeError("COOKIE_SECURE must be True in production")
    if not settings.STORAGE_USE_SSL:
        raise RuntimeError("STORAGE_USE_SSL must be True in production")
from backend.modules.content_strategy.service import ContentStrategyService
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.identity_access.service import IdentityService
from backend.modules.publishing.schemas import SocialAccountUpsertRequest
from backend.modules.publishing.service import PublishingService
from backend.modules.source_ingestion.schemas import SourceCreateRequest
from backend.modules.source_ingestion.service import SourceIngestionService


async def bootstrap_application(db: AsyncSession) -> None:
    _assert_production_secrets()
    identity_service = IdentityService(db)
    await identity_service.ensure_system_roles_and_permissions()

    if not settings.DEMO_SEED_ENABLED:
        await db.commit()
        return

    repo = IdentityRepository(db)
    demo_user = await repo.get_user_by_email(settings.DEMO_ADMIN_EMAIL.lower())
    if demo_user:
        await db.commit()
        return

    demo_user = await identity_service.sign_up(
        settings.DEMO_ADMIN_EMAIL,
        settings.DEMO_ADMIN_PASSWORD,
        settings.DEMO_ADMIN_NAME,
    )
    if not demo_user.default_tenant_id:
        await db.commit()
        return

    strategy_service = ContentStrategyService(db)
    await strategy_service.get_or_create_brand_profile(demo_user.default_tenant_id)

    publishing_service = PublishingService(db)
    for platform in ["youtube", "instagram", "tiktok", "x", "bluesky"]:
        await publishing_service.upsert_social_account(
            demo_user.default_tenant_id,
            SocialAccountUpsertRequest(
                platform=platform,
                display_name=f"Demo {platform.title()}",
                handle=f"demo_{platform}",
                use_stub=True,
                metadata={"seeded": "true"},
            ),
        )

    ingestion_service = SourceIngestionService(db)
    for source_name, source_type, url in [
        ("TechCrunch", "rss", "https://techcrunch.com/feed/"),
        ("Hacker News", "rss", "https://hnrss.org/frontpage"),
    ]:
        await ingestion_service.create_source(
            demo_user.default_tenant_id,
            SourceCreateRequest(
                name=source_name,
                source_type=source_type,
                url=url,
                category="technology",
                trust_score=0.8,
            ),
        )
    await db.commit()
