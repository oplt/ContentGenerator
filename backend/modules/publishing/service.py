from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import decrypt_secret, encrypt_secret, resolve_secret_reference
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.models import (
    ConnectedAccount,
    ConnectedAccountStatus,
    PublishedPost,
    PublishedPostStatus,
    PublishingJob,
    PublishingJobStatus,
    SocialAccount,
    SocialAccountToken,
)
from backend.modules.publishing.providers import AuthValidationResult, get_provider
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.publishing.schemas import (
    ConnectedAccountValidationResponse,
    PublishNowRequest,
    PublishingJobActionResponse,
    SocialAccountUpsertRequest,
)
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class PublishingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PublishingRepository(db)
        self.content_repo = ContentGenerationRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)

    async def list_social_accounts(self, tenant_id: UUID) -> list[SocialAccount]:
        return await self.repo.list_social_accounts(tenant_id)

    async def list_connected_accounts(self, tenant_id: UUID) -> list[ConnectedAccount]:
        return await self.repo.list_connected_accounts(tenant_id)

    async def upsert_social_account(self, tenant_id: UUID, payload: SocialAccountUpsertRequest) -> SocialAccount:
        existing = await self.repo.get_social_account_by_platform(tenant_id, payload.platform)
        connected = await self.repo.get_connected_account_by_platform(tenant_id, payload.platform)
        provider = get_provider(
            payload.platform,
            use_stub=payload.use_stub,
            access_token=payload.access_token or "",
            account_external_id=payload.account_external_id or "",
        )
        capability_flags = provider.capabilities()
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
        credential_ref = None
        if payload.access_token or payload.access_token_secret_ref:
            await self.repo.upsert_token(
                SocialAccountToken(
                    social_account_id=account.id,
                    access_token_encrypted=encrypt_secret(payload.access_token) if payload.access_token else encrypt_secret(f"secret-ref:{payload.access_token_secret_ref}"),
                    refresh_token_encrypted=encrypt_secret(payload.refresh_token) if payload.refresh_token else None,
                    scopes=payload.scopes,
                )
            )
            if payload.access_token_secret_ref:
                credential_ref = encrypt_secret(payload.access_token_secret_ref)
            else:
                credential_ref = f"social-account-token:{account.id}"
        account_mode = payload.metadata | {"mode": "stub" if payload.use_stub else "real"}
        if connected:
            connected.social_account_id = account.id
            connected.account_name = payload.display_name
            connected.auth_type = "stub" if payload.use_stub else "oauth"
            connected.credential_ref = credential_ref or connected.credential_ref
            connected.scopes = payload.scopes
            connected.account_metadata = account_mode
            connected.status = ConnectedAccountStatus.ACTIVE.value
        else:
            await self.repo.create_connected_account(
                ConnectedAccount(
                    tenant_id=tenant_id,
                    social_account_id=account.id,
                    platform=payload.platform,
                    account_name=payload.display_name,
                    auth_type="stub" if payload.use_stub else "oauth",
                    credential_ref=credential_ref,
                    scopes=payload.scopes,
                    account_metadata=account_mode,
                    status=ConnectedAccountStatus.ACTIVE.value,
                )
            )
        validation = await provider.validate_auth(social_account=account)
        account.status = validation.account_status
        return account

    async def validate_connected_account(
        self,
        tenant_id: UUID,
        connected_account_id: UUID,
    ) -> ConnectedAccountValidationResponse:
        connected = await self.repo.get_connected_account(tenant_id, connected_account_id)
        if not connected:
            raise HTTPException(status_code=404, detail="Connected account not found")
        social_account = None
        if connected.social_account_id:
            social_account = await self.repo.get_social_account(tenant_id, connected.social_account_id)
        if not social_account:
            raise HTTPException(status_code=404, detail="Social account not found")
        token_row = await self.repo.get_token_for_account(social_account.id)
        access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
        if access_token.startswith("secret-ref:"):
            access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""
        provider = get_provider(
            str(connected.platform),
            use_stub=social_account.account_metadata.get("mode") == "stub",
            access_token=access_token,
            account_external_id=social_account.account_external_id or "",
        )
        validation: AuthValidationResult = await provider.validate_auth(social_account=social_account)
        connected.status = validation.account_status
        social_account.status = validation.account_status
        await self.db.flush()
        return ConnectedAccountValidationResponse(
            connected_account_id=connected.id,
            platform=str(connected.platform),
            is_valid=validation.is_valid,
            account_status=validation.account_status,
            detail=validation.detail,
        )

    @staticmethod
    def _build_recovery_actions(platform: str, failure_reason: str | None = None) -> list[str]:
        actions = ["retry_publish", "open_manual_publish_runbook", "reauthorize_account"]
        if failure_reason:
            actions.append(f"review_failure:{failure_reason[:80]}")
        if platform in {"x", "bluesky"}:
            actions.append("manual_delete_if_duplicate")
        return actions

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
        grounding = content_job.grounding_bundle if isinstance(getattr(content_job, "grounding_bundle", None), dict) else {}
        risk_review = grounding.get("risk_review", {})
        risk_label = str((risk_review or {}).get("label") or grounding.get("risk_label") or "low")
        if risk_label == "blocked":
            raise HTTPException(status_code=422, detail="Risk review blocked this content from publishing")
        assets = await self.content_repo.list_assets(content_job.id)

        # Decrypt access token for real publishing (X, Bluesky)
        token_row = await self.repo.get_token_for_account(social_account.id) if social_account.id else None
        access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
        if access_token.startswith("secret-ref:"):
            access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""

        use_stub = social_account.account_metadata.get("mode") == "stub"
        provider = get_provider(
            job.platform,
            use_stub=use_stub,
            access_token=access_token,
            account_external_id=social_account.account_external_id or "",
            dry_run=job.dry_run,
        )
        validation = await provider.validate_auth(social_account=social_account)
        if not validation.is_valid and not use_stub:
            raise HTTPException(status_code=400, detail=validation.detail or "Publishing credentials are invalid")
        draft = await provider.create_draft(social_account=social_account, assets=assets)
        publish_attempt_key = f"{job.id}:{job.platform}:{job.retry_count}"
        result = await provider.publish_now(
            social_account=social_account,
            assets=assets,
            publish_attempt_key=publish_attempt_key,
        )
        job.provider = provider.platform
        if result.manual_required:
            job.status = PublishingJobStatus.MANUAL_REQUIRED.value
        elif result.status == PublishingJobStatus.SUCCEEDED_DRY_RUN.value:
            job.status = PublishingJobStatus.SUCCEEDED_DRY_RUN.value
        else:
            job.status = PublishingJobStatus.SUCCEEDED.value
        job.published_at = datetime.now(timezone.utc)
        job.external_post_id = result.external_post_id
        job.external_post_url = result.external_post_url or await provider.fetch_post_url(
            social_account=social_account,
            external_post_id=result.external_post_id,
            provider_payload=result.payload,
        )
        job.provider_payload = {
            **result.payload,
            "draft_preview": draft.preview_text,
            "draft_status": draft.status,
            "publish_attempt_key": publish_attempt_key,
            "auth_status": validation.account_status,
            "recovery_actions": ",".join(self._build_recovery_actions(job.platform)),
        }
        await self.repo.create_published_post(
            PublishedPost(
                tenant_id=tenant_id,
                social_account_id=social_account.id,
                publishing_job_id=job.id,
                platform=job.platform,
                post_type="video" if any(asset.asset_type == "video" for asset in assets) else "text",
                external_post_id=result.external_post_id,
                external_url=job.external_post_url,
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
        content_job = await self.content_repo.get_job(tenant_id, job.content_job_id)
        if content_job:
            from backend.modules.content_strategy.repository import ContentStrategyRepository

            plan = await ContentStrategyRepository(self.db).get_content_plan(tenant_id, content_job.content_plan_id)
            if plan:
                cluster = await self.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.PUBLISHED.value
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
        new_jobs: list[PublishingJob] = []  # only jobs created this call need publishing
        for platform in platforms:
            idempotency_key = payload.idempotency_key or f"{content_job.id}:{platform}"
            existing = await self.repo.get_job_by_idempotency(idempotency_key)
            if existing:
                jobs.append(existing)
                continue
            social_account = await self.repo.get_social_account_by_platform(tenant_id, platform)
            if not social_account:
                raise HTTPException(status_code=400, detail=f"No social account configured for {platform}")
            connected_account = await self.repo.get_connected_account_by_platform(tenant_id, platform)
            provider = get_provider(
                platform,
                use_stub=social_account.account_metadata.get("mode") == "stub",
                access_token="",
                account_external_id=social_account.account_external_id or "",
                dry_run=payload.dry_run,
            )
            schedule_result = None
            if payload.scheduled_for:
                schedule_result = await provider.schedule_publish(
                    social_account=social_account,
                    assets=assets,
                    scheduled_for=payload.scheduled_for,
                )
            job = await self.repo.create_publishing_job(
                PublishingJob(
                    tenant_id=tenant_id,
                    content_job_id=content_job.id,
                    social_account_id=social_account.id,
                    connected_account_id=connected_account.id if connected_account else None,
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
            if schedule_result:
                job.provider_payload = {
                    **schedule_result.payload,
                    "native_scheduling_supported": str(schedule_result.native_supported).lower(),
                }
            jobs.append(job)
            new_jobs.append(job)

        if payload.scheduled_for is None:
            for job in new_jobs:
                await self._publish_job(tenant_id, job)
        await self.db.flush()
        return jobs

    async def execute_due_jobs(self, worker_id: str | None = None) -> list[PublishingJob]:
        """
        Claim and execute due publishing jobs.

        Uses FOR UPDATE SKIP LOCKED so concurrent workers never process the same job.
        """
        import uuid as _uuid
        effective_worker_id = worker_id or str(_uuid.uuid4())
        claimed = await self.repo.claim_due_jobs(
            worker_id=effective_worker_id, batch_size=50
        )
        executed: list[PublishingJob] = []
        for job in claimed:
            try:
                executed.append(await self._publish_job(job.tenant_id, job))
            except Exception as exc:
                job.failure_reason = str(exc)[:500]
                job.retry_count = (job.retry_count or 0) + 1
                if job.retry_count >= 3:
                    job.status = PublishingJobStatus.DEAD.value
                    job.dead_lettered_at = datetime.now(timezone.utc)
                    job.dead_letter_reason = job.failure_reason
                    job.provider_payload = {
                        **(job.provider_payload or {}),
                        "recovery_actions": ",".join(self._build_recovery_actions(job.platform, job.failure_reason)),
                        "dead_letter": "true",
                    }
                    await self.audit.record(
                        tenant_id=job.tenant_id,
                        actor_user_id=None,
                        action="publishing.dead_lettered",
                        entity_type="publishing_job",
                        entity_id=str(job.id),
                        message="Publishing job moved to dead-letter state",
                        payload={"platform": job.platform, "failure_reason": job.failure_reason or ""},
                        severity="warning",
                        outcome="dead_lettered",
                        payload_schema="publishing.dead_letter.v1",
                    )
                else:
                    backoff_minutes = 2 ** job.retry_count
                    job.status = PublishingJobStatus.SCHEDULED.value
                    job.scheduled_for = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
                    job.provider_payload = {
                        **(job.provider_payload or {}),
                        "recovery_actions": ",".join(self._build_recovery_actions(job.platform, job.failure_reason)),
                        "next_retry_at": job.scheduled_for.isoformat(),
                        "backoff_minutes": str(backoff_minutes),
                    }
                await self.db.flush()
        return executed

    async def list_jobs(self, tenant_id: UUID) -> list[PublishingJob]:
        return await self.repo.list_publishing_jobs(tenant_id)

    async def list_published_posts(self, tenant_id: UUID) -> list[PublishedPost]:
        return await self.repo.list_published_posts(tenant_id)

    async def cancel_scheduled_job(self, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
        job = await self.repo.get_publishing_job(tenant_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Publishing job not found")
        if job.status not in {
            PublishingJobStatus.SCHEDULED.value,
            PublishingJobStatus.PENDING.value,
            PublishingJobStatus.FAILED.value,
        }:
            raise HTTPException(status_code=409, detail="Only pending or scheduled jobs can be cancelled")
        job.status = PublishingJobStatus.CANCELLED.value
        job.failure_reason = "cancelled_by_operator"
        job.scheduled_for = None
        job.provider_payload = {
            **(job.provider_payload or {}),
            "recovery_actions": "retry_publish",
        }
        await self.db.flush()
        return PublishingJobActionResponse(job_id=job.id, status=job.status, detail="Publishing job cancelled")

    async def retry_job(self, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
        job = await self.repo.get_publishing_job(tenant_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Publishing job not found")
        if job.status not in {
            PublishingJobStatus.FAILED.value,
            PublishingJobStatus.DEAD.value,
            PublishingJobStatus.CANCELLED.value,
            PublishingJobStatus.MANUAL_REQUIRED.value,
        }:
            raise HTTPException(status_code=409, detail="Only failed, dead-lettered, cancelled, or manual jobs can be retried")
        job.status = PublishingJobStatus.PENDING.value
        job.failure_reason = None
        job.dead_letter_reason = None
        job.dead_lettered_at = None
        job.scheduled_for = None
        job.provider_payload = {
            **(job.provider_payload or {}),
            "retried_by_operator": "true",
        }
        await self.db.flush()
        return PublishingJobActionResponse(job_id=job.id, status=job.status, detail="Publishing job queued for retry")
