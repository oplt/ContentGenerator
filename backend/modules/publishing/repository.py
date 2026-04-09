from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.models import (
    ConnectedAccount,
    PublishedPost,
    PublishingJob,
    PublishingJobStatus,
    SocialAccount,
    SocialAccountToken,
)


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

    async def get_connected_account_by_platform(self, tenant_id: UUID, platform: str) -> ConnectedAccount | None:
        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.tenant_id == tenant_id,
                ConnectedAccount.platform == platform,
                ConnectedAccount.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_connected_accounts(self, tenant_id: UUID) -> list[ConnectedAccount]:
        result = await self.db.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.tenant_id == tenant_id,
                ConnectedAccount.deleted_at.is_(None),
            )
            .order_by(ConnectedAccount.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_connected_account(self, tenant_id: UUID, connected_account_id: UUID) -> ConnectedAccount | None:
        result = await self.db.execute(
            select(ConnectedAccount).where(
                ConnectedAccount.tenant_id == tenant_id,
                ConnectedAccount.id == connected_account_id,
                ConnectedAccount.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def create_social_account(self, account: SocialAccount) -> SocialAccount:
        self.db.add(account)
        await self.db.flush()
        return account

    async def create_connected_account(self, account: ConnectedAccount) -> ConnectedAccount:
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

    async def claim_due_jobs(self, worker_id: str, batch_size: int = 50) -> list[PublishingJob]:
        """
        Atomically claim up to `batch_size` due publishing jobs.

        Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent multiple workers from
        processing the same job concurrently (double-publish prevention).

        Returns the list of claimed jobs (status already set to CLAIMED in DB).
        """
        now = datetime.now(timezone.utc)
        # Step 1: select candidate IDs with row-level locks, skipping already-locked rows
        subq = (
            select(PublishingJob.id)
            .where(
                PublishingJob.status.in_(
                    [PublishingJobStatus.PENDING.value, PublishingJobStatus.SCHEDULED.value]
                ),
                PublishingJob.scheduled_for.is_not(None),
                PublishingJob.scheduled_for <= now,
                PublishingJob.claimed_at.is_(None),
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(subq)
        job_ids = [row[0] for row in result.fetchall()]
        if not job_ids:
            return []

        # Step 2: atomically mark them as CLAIMED
        await self.db.execute(
            update(PublishingJob)
            .where(PublishingJob.id.in_(job_ids))
            .values(
                status=PublishingJobStatus.CLAIMED.value,
                claimed_at=now,
                worker_id=worker_id,
            )
        )
        await self.db.flush()

        # Step 3: reload the updated rows
        reloaded = await self.db.execute(
            select(PublishingJob).where(PublishingJob.id.in_(job_ids))
        )
        return list(reloaded.scalars().all())

    async def get_token_for_account(self, social_account_id: UUID) -> SocialAccountToken | None:
        result = await self.db.execute(
            select(SocialAccountToken)
            .where(
                SocialAccountToken.social_account_id == social_account_id,
                SocialAccountToken.deleted_at.is_(None),
            )
            .order_by(SocialAccountToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_due_jobs(self) -> list[PublishingJob]:
        """Deprecated: use claim_due_jobs() for race-condition-safe claiming."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(PublishingJob).where(
                PublishingJob.status.in_(["pending", "scheduled"]),
                PublishingJob.scheduled_for.is_not(None),
                PublishingJob.scheduled_for <= now,
            )
        )
        return list(result.scalars().all())
