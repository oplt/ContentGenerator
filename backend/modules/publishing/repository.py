from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.job_claiming import JobClaimingMixin
from backend.modules.publishing.models import (
    ConnectedAccount,
    ConnectedAccountStatus,
    PublishedPost,
    PublishingAttempt,
    PublishingJob,
    SocialAccount,
    SocialAccountStatus,
    SocialAccountToken,
)


class PublishingRepository(JobClaimingMixin):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_social_accounts(self, tenant_id: UUID) -> list[SocialAccount]:
        result = await self.db.execute(
            select(SocialAccount)
            .where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.deleted_at.is_(None),
                SocialAccount.status != SocialAccountStatus.QUARANTINED.value,
            )
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

    async def get_social_accounts_by_ids(
        self, tenant_id: UUID, account_ids: list[UUID]
    ) -> list[SocialAccount]:
        if not account_ids:
            return []
        result = await self.db.execute(
            select(SocialAccount).where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.id.in_(account_ids),
                SocialAccount.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    async def get_social_account_by_external_id(
        self,
        tenant_id: UUID,
        platform: str,
        account_external_id: str,
    ) -> SocialAccount | None:
        result = await self.db.execute(
            select(SocialAccount).where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.platform == platform,
                SocialAccount.account_external_id == account_external_id,
                SocialAccount.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_social_account_by_platform(self, tenant_id: UUID, platform: str) -> SocialAccount | None:
        """Platform-only compat: oldest non-quarantined account (multi-account → use external id)."""
        result = await self.db.execute(
            select(SocialAccount)
            .where(
                SocialAccount.tenant_id == tenant_id,
                SocialAccount.platform == platform,
                SocialAccount.deleted_at.is_(None),
                SocialAccount.status != SocialAccountStatus.QUARANTINED.value,
            )
            .order_by(SocialAccount.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_connected_account_by_platform(self, tenant_id: UUID, platform: str) -> ConnectedAccount | None:
        result = await self.db.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.tenant_id == tenant_id,
                ConnectedAccount.platform == platform,
                ConnectedAccount.deleted_at.is_(None),
                ConnectedAccount.status != ConnectedAccountStatus.QUARANTINED.value,
            )
            .order_by(ConnectedAccount.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_connected_for_social(
        self, tenant_id: UUID, social_account_id: UUID
    ) -> ConnectedAccount | None:
        result = await self.db.execute(
            select(ConnectedAccount)
            .where(
                ConnectedAccount.tenant_id == tenant_id,
                ConnectedAccount.social_account_id == social_account_id,
                ConnectedAccount.deleted_at.is_(None),
            )
            .order_by(ConnectedAccount.created_at.asc())
            .limit(1)
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
        """Replace active credential binding (at most one active per social account)."""
        existing = await self.get_token_for_account(token.social_account_id)
        next_version = 1
        if existing is not None:
            next_version = int(existing.binding_version or 1) + 1
            existing.is_active = False
            await self.db.flush()
        token.is_active = True
        token.binding_version = next_version
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

    async def get_published_post_for_job(self, publishing_job_id: UUID) -> PublishedPost | None:
        result = await self.db.execute(
            select(PublishedPost)
            .where(PublishedPost.publishing_job_id == publishing_job_id)
            .order_by(PublishedPost.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_published_posts(self, tenant_id: UUID, limit: int = 100) -> list[PublishedPost]:
        result = await self.db.execute(
            select(PublishedPost)
            .where(PublishedPost.tenant_id == tenant_id)
            .order_by(PublishedPost.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_attempt(self, attempt: PublishingAttempt) -> PublishingAttempt:
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_attempt_by_key(self, attempt_key: str) -> PublishingAttempt | None:
        result = await self.db.execute(
            select(PublishingAttempt).where(PublishingAttempt.attempt_key == attempt_key)
        )
        return result.scalar_one_or_none()

    async def get_token_for_account(self, social_account_id: UUID) -> SocialAccountToken | None:
        result = await self.db.execute(
            select(SocialAccountToken)
            .where(
                SocialAccountToken.social_account_id == social_account_id,
                SocialAccountToken.deleted_at.is_(None),
                SocialAccountToken.is_active.is_(True),
            )
            .order_by(SocialAccountToken.created_at.desc())
            .limit(1)
        )
        token = result.scalar_one_or_none()
        if token is not None:
            return token
        # Dual-read: pre-migration rows may lack is_active semantics.
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

    async def get_tokens_for_accounts(
        self, social_account_ids: list[UUID]
    ) -> dict[UUID, SocialAccountToken]:
        """Latest active (else latest non-deleted) token per social account."""
        if not social_account_ids:
            return {}
        result = await self.db.execute(
            select(SocialAccountToken)
            .where(
                SocialAccountToken.social_account_id.in_(social_account_ids),
                SocialAccountToken.deleted_at.is_(None),
            )
            .order_by(
                SocialAccountToken.social_account_id.asc(),
                SocialAccountToken.is_active.desc(),
                SocialAccountToken.created_at.desc(),
            )
        )
        latest: dict[UUID, SocialAccountToken] = {}
        for token in result.scalars().all():
            if token.social_account_id not in latest:
                latest[token.social_account_id] = token
        return latest
