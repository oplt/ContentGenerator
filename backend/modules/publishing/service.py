from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import encrypt_secret
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.models import PublishedPost, PublishingJob, PublishingJobStatus, PublishedPostStatus, SocialAccount, SocialAccountToken
from backend.modules.publishing.providers import get_provider
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.publishing.schemas import PublishNowRequest, SocialAccountUpsertRequest


class PublishingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PublishingRepository(db)
        self.content_repo = ContentGenerationRepository(db)
        self.audit = AuditService(db)

    async def list_social_accounts(self, tenant_id: UUID) -> list[SocialAccount]:
        return await self.repo.list_social_accounts(tenant_id)

    async def upsert_social_account(self, tenant_id: UUID, payload: SocialAccountUpsertRequest) -> SocialAccount:
        existing = await self.repo.get_social_account_by_platform(tenant_id, payload.platform)
        capability_flags = get_provider(payload.platform, use_stub=payload.use_stub).capabilities()
        if existing:
            existing.display_name = payload.display_name
            existing.handle = payload.handle
            existing.account_external_id = payload.account_external_id
            existing.account_metadata = payload.metadata | {"mode": "stub" if payload.use_stub else "real"}
            existing.capability_flags = capability_flags
            account = existing
        else:
            account = await self.repo.create_social_account(
                SocialAccount(
                    tenant_id=tenant_id,
                    platform=payload.platform,
                    display_name=payload.display_name,
                    handle=payload.handle,
                    account_external_id=payload.account_external_id,
                    account_metadata=payload.metadata | {"mode": "stub" if payload.use_stub else "real"},
                    capability_flags=capability_flags,
                )
            )
        if payload.access_token:
            await self.repo.upsert_token(
                SocialAccountToken(
                    social_account_id=account.id,
                    access_token_encrypted=encrypt_secret(payload.access_token),
                    refresh_token_encrypted=encrypt_secret(payload.refresh_token) if payload.refresh_token else None,
                    scopes=payload.scopes,
                )
            )
        return account

    async def _publish_job(self, tenant_id: UUID, job: PublishingJob) -> PublishingJob:
        social_account = (
            await self.repo.get_social_account(tenant_id, job.social_account_id)
            if job.social_account_id
            else None
        )
        if not social_account:
            raise HTTPException(status_code=400, detail="No connected social account for publishing job")
        content_job = await self.content_repo.get_job(tenant_id, job.content_job_id)
        if not content_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.content_repo.list_assets(content_job.id)
        provider = get_provider(job.platform, use_stub=social_account.account_metadata.get("mode") == "stub")
        result = await provider.publish(social_account=social_account, assets=assets)
        job.provider = provider.platform
        job.status = (
            PublishingJobStatus.MANUAL_REQUIRED.value
            if result.manual_required
            else PublishingJobStatus.SUCCEEDED.value
        )
        job.published_at = datetime.now(timezone.utc)
        job.external_post_id = result.external_post_id
        job.external_post_url = result.external_post_url
        job.provider_payload = result.payload
        await self.repo.create_published_post(
            PublishedPost(
                tenant_id=tenant_id,
                social_account_id=social_account.id,
                publishing_job_id=job.id,
                platform=job.platform,
                post_type="video" if any(asset.asset_type == "video" for asset in assets) else "text",
                external_post_id=result.external_post_id,
                external_url=result.external_post_url,
                status=(
                    PublishedPostStatus.MANUAL.value
                    if result.manual_required
                    else PublishedPostStatus.LIVE.value
                ),
                published_at=job.published_at,
                raw_payload=result.payload,
                analytics_sync_state="pending",
            )
        )
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="publishing.job_executed",
            entity_type="publishing_job",
            entity_id=str(job.id),
            message="Publishing job executed",
            payload={"platform": job.platform, "status": job.status},
        )
        await self.db.flush()
        return job

    async def publish_now(
        self,
        *,
        tenant_id: UUID,
        approval_request_id: UUID | None,
        payload: PublishNowRequest,
    ) -> list[PublishingJob]:
        content_job = await self.content_repo.get_job(tenant_id, payload.content_job_id)
        if not content_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.content_repo.list_assets(content_job.id)
        detected_platforms = {
            asset.platform
            for asset in assets
            if asset.platform and asset.asset_type == "text_variant"
        }
        platforms = payload.platforms or sorted(detected_platforms)
        if not platforms:
            raise HTTPException(status_code=400, detail="No target platforms available for publish")

        jobs: list[PublishingJob] = []
        for platform in platforms:
            idempotency_key = payload.idempotency_key or f"{content_job.id}:{platform}"
            existing = await self.repo.get_job_by_idempotency(idempotency_key)
            if existing:
                jobs.append(existing)
                continue
            social_account = await self.repo.get_social_account_by_platform(tenant_id, platform)
            if not social_account:
                raise HTTPException(status_code=400, detail=f"No social account configured for {platform}")
            job = await self.repo.create_publishing_job(
                PublishingJob(
                    tenant_id=tenant_id,
                    content_job_id=content_job.id,
                    social_account_id=social_account.id,
                    approval_request_id=approval_request_id,
                    platform=platform,
                    provider=social_account.account_metadata.get("mode", "stub"),
                    idempotency_key=idempotency_key,
                    dry_run=payload.dry_run,
                    scheduled_for=payload.scheduled_for,
                    status=(
                        PublishingJobStatus.SCHEDULED.value
                        if payload.scheduled_for
                        else PublishingJobStatus.PENDING.value
                    ),
                )
            )
            jobs.append(job)

        if payload.scheduled_for is None:
            for job in jobs:
                await self._publish_job(tenant_id, job)
        await self.db.flush()
        return jobs

    async def execute_due_jobs(self) -> list[PublishingJob]:
        executed: list[PublishingJob] = []
        for job in await self.repo.list_due_jobs():
            executed.append(await self._publish_job(job.tenant_id, job))
        return executed

    async def list_jobs(self, tenant_id: UUID) -> list[PublishingJob]:
        return await self.repo.list_publishing_jobs(tenant_id)

    async def list_published_posts(self, tenant_id: UUID) -> list[PublishedPost]:
        return await self.repo.list_published_posts(tenant_id)
