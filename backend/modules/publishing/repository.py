from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.models import PublishedPost, PublishingJob, SocialAccount, SocialAccountToken


class PublishingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_social_accounts(self, tenant_id: UUID) -> list[SocialAccount]:
        result = await self.db.execute(
            select(SocialAccount)
            .where(SocialAccount.tenant_id == tenant_id, SocialAccount.deleted_at.is_(None))
            .order_by(SocialAccount.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_social_account(self, tenant_id: UUID, account_id: UUID) -> SocialAccount | None:
        result = await self.db.execute(
            select(SocialAccount).where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.id == account_id,
                SocialAccount.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_social_account_by_platform(self, tenant_id: UUID, platform: str) -> SocialAccount | None:
        result = await self.db.execute(
            select(SocialAccount).where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.platform == platform,
                SocialAccount.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_social_account(self, account: SocialAccount) -> SocialAccount:
        self.db.add(account)
        await self.db.flush()
        return account

    async def upsert_token(self, token: SocialAccountToken) -> SocialAccountToken:
        self.db.add(token)
        await self.db.flush()
        return token

    async def create_publishing_job(self, job: PublishingJob) -> PublishingJob:
        self.db.add(job)
        await self.db.flush()
        return job

    async def get_publishing_job(self, tenant_id: UUID, job_id: UUID) -> PublishingJob | None:
        result = await self.db.execute(
            select(PublishingJob).where(PublishingJob.id == job_id, PublishingJob.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_job_by_idempotency(self, idempotency_key: str) -> PublishingJob | None:
        result = await self.db.execute(
            select(PublishingJob).where(PublishingJob.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def list_publishing_jobs(self, tenant_id: UUID, limit: int = 100) -> list[PublishingJob]:
        result = await self.db.execute(
            select(PublishingJob)
            .where(PublishingJob.tenant_id == tenant_id)
            .order_by(PublishingJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_published_post(self, post: PublishedPost) -> PublishedPost:
        self.db.add(post)
        await self.db.flush()
        return post

    async def list_published_posts(self, tenant_id: UUID, limit: int = 100) -> list[PublishedPost]:
        result = await self.db.execute(
            select(PublishedPost)
            .where(PublishedPost.tenant_id == tenant_id)
            .order_by(PublishedPost.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_due_jobs(self) -> list[PublishingJob]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(PublishingJob).where(
                PublishingJob.status.in_(["pending", "scheduled"]),
                PublishingJob.scheduled_for.is_not(None),
                PublishingJob.scheduled_for <= now,
            )
        )
        return list(result.scalars().all())
