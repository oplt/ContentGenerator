from __future__ import annotations

from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.security import decrypt_secret, encrypt_secret, resolve_secret_reference
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.account_ops import (
    build_account_display_snapshot,
    consume_publish_quota,
    consume_retry_quota,
    schedule_local_to_utc,
)
from backend.modules.publishing.account_selection import (
    build_publish_idempotency_key,
    resolve_social_accounts,
    variant_fingerprint,
)
from backend.modules.publishing.failure_classification import PublishErrorClass, classify_publish_error
from backend.modules.publishing.account_lineage import resolve_external_id
from backend.modules.publishing.attempt_lifecycle import PublishAttemptLifecycle
from backend.modules.publishing.job_executor import publish_job
from backend.modules.publishing.models import (
    ConnectedAccount,
    ConnectedAccountStatus,
    PublishedPost,
    PublishedPostStatus,
    PublishingAttempt,
    PublishingAttemptStatus,
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
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class PublishingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PublishingRepository(db)
        self.content_repo = ContentGenerationRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)
        self.attempts = PublishAttemptLifecycle(
            db,
            repo=self.repo,
            content_repo=self.content_repo,
            story_repo=self.story_repo,
            audit=self.audit,
        )

    async def list_social_accounts(self, tenant_id: UUID) -> list[SocialAccount]:
        return await self.repo.list_social_accounts(tenant_id)

    async def list_connected_accounts(self, tenant_id: UUID) -> list[ConnectedAccount]:
        return await self.repo.list_connected_accounts(tenant_id)

    async def upsert_social_account(self, tenant_id: UUID, payload: SocialAccountUpsertRequest) -> SocialAccount:
        """Upsert canonical SocialAccount and dual-write ConnectedAccount projection."""
        auth_type = "stub" if payload.use_stub else "oauth"
        existing: SocialAccount | None = None
        if payload.account_external_id:
            existing = await self.repo.get_social_account_by_external_id(
                tenant_id, payload.platform, payload.account_external_id.strip()
            )
        if existing is None:
            # Platform-only compat for single-account tenants / stub connects.
            existing = await self.repo.get_social_account_by_platform(tenant_id, payload.platform)
            if (
                existing is not None
                and payload.account_external_id
                and existing.account_external_id
                and existing.account_external_id != payload.account_external_id.strip()
                and not str(existing.account_external_id).startswith("legacy:")
            ):
                # Distinct provider identity → create additional account (multi-account).
                existing = None

        connected = None
        if existing is not None:
            connected = await self.repo.get_connected_for_social(tenant_id, existing.id)
        if connected is None:
            connected = await self.repo.get_connected_account_by_platform(tenant_id, payload.platform)

        provider = get_provider(
            payload.platform,
            use_stub=payload.use_stub,
            access_token=payload.access_token or "",
            account_external_id=payload.account_external_id or "",
        )
        capability_flags = provider.capabilities()
        account_mode: dict[str, object] = {**payload.metadata, "mode": "stub" if payload.use_stub else "real"}

        if existing:
            existing.display_name = payload.display_name
            existing.handle = payload.handle
            existing.auth_type = auth_type
            existing.account_metadata = {str(k): str(v) for k, v in account_mode.items()}
            existing.capability_flags = capability_flags
            if payload.account_external_id:
                existing.account_external_id = payload.account_external_id.strip()
            elif not existing.account_external_id:
                existing.account_external_id = resolve_external_id(
                    provided=None,
                    connected_id=connected.id if connected else None,
                    social_id=existing.id,
                )
            account = existing
        else:
            account = await self.repo.create_social_account(
                SocialAccount(
                    tenant_id=tenant_id,
                    platform=payload.platform,
                    display_name=payload.display_name,
                    handle=payload.handle,
                    account_external_id=payload.account_external_id.strip()
                    if payload.account_external_id
                    else None,
                    auth_type=auth_type,
                    account_metadata={str(k): str(v) for k, v in account_mode.items()},
                    capability_flags=capability_flags,
                    settings={},
                    legacy_connected_account_id=connected.id if connected else None,
                )
            )
            if not account.account_external_id:
                account.account_external_id = resolve_external_id(
                    provided=None,
                    connected_id=connected.id if connected else None,
                    social_id=account.id,
                )

        credential_ref = None
        if payload.access_token or payload.access_token_secret_ref:
            await self.repo.upsert_token(
                SocialAccountToken(
                    social_account_id=account.id,
                    access_token_encrypted=encrypt_secret(payload.access_token)
                    if payload.access_token
                    else encrypt_secret(f"secret-ref:{payload.access_token_secret_ref}"),
                    refresh_token_encrypted=encrypt_secret(payload.refresh_token)
                    if payload.refresh_token
                    else None,
                    scopes=payload.scopes,
                )
            )
            if payload.access_token_secret_ref:
                credential_ref = encrypt_secret(payload.access_token_secret_ref)
            else:
                credential_ref = f"social-account-token:{account.id}"

        if connected:
            connected.social_account_id = account.id
            connected.account_name = payload.display_name
            connected.auth_type = auth_type
            connected.credential_ref = credential_ref or connected.credential_ref
            connected.scopes = payload.scopes
            connected.account_metadata = account_mode
            connected.status = ConnectedAccountStatus.ACTIVE.value
            account.legacy_connected_account_id = connected.id
        else:
            connected = await self.repo.create_connected_account(
                ConnectedAccount(
                    tenant_id=tenant_id,
                    social_account_id=account.id,
                    platform=payload.platform,
                    account_name=payload.display_name,
                    auth_type=auth_type,
                    credential_ref=credential_ref,
                    scopes=payload.scopes,
                    account_metadata=account_mode,
                    status=ConnectedAccountStatus.ACTIVE.value,
                )
            )
            account.legacy_connected_account_id = connected.id

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
        return PublishAttemptLifecycle.build_recovery_actions(platform, failure_reason)

    @staticmethod
    def build_attempt_key(job: PublishingJob, attempt_number: int) -> str:
        return PublishAttemptLifecycle.build_attempt_key(job, attempt_number)

    async def _prepare_attempt(
        self,
        job: PublishingJob,
        *,
        worker_id: str | None,
    ) -> PublishingAttempt:
        return await self.attempts.prepare_attempt(job, worker_id=worker_id)

    async def _finalize_success(
        self,
        *,
        tenant_id: UUID,
        job: PublishingJob,
        attempt: PublishingAttempt,
        social_account: SocialAccount,
        result: Any,
        draft_preview: str,
        draft_status: str,
        auth_status: str,
        publish_attempt_key: str,
        post_type: str,
    ) -> PublishingJob:
        return await self.attempts.finalize_success(
            tenant_id=tenant_id,
            job=job,
            attempt=attempt,
            social_account=social_account,
            result=result,
            draft_preview=draft_preview,
            draft_status=draft_status,
            auth_status=auth_status,
            publish_attempt_key=publish_attempt_key,
            post_type=post_type,
        )

    async def _finalize_failure(
        self,
        *,
        job: PublishingJob,
        attempt: PublishingAttempt,
        exc: BaseException,
        error_class: PublishErrorClass,
    ) -> None:
        await self.attempts.finalize_failure(
            job=job,
            attempt=attempt,
            exc=exc,
            error_class=error_class,
        )

    async def _publish_job(
        self,
        tenant_id: UUID,
        job: PublishingJob,
        *,
        worker_id: str | None = None,
        commit_boundaries: bool = False,
    ) -> PublishingJob:
        return await publish_job(
            self,
            tenant_id,
            job,
            worker_id=worker_id,
            commit_boundaries=commit_boundaries,
        )

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
        legacy_platforms = payload.platforms or (
            None if (payload.social_account_ids or content_job.target_social_account_ids) else sorted(detected_platforms)
        )

        accounts = await resolve_social_accounts(
            repo=self.repo,
            tenant_id=tenant_id,
            social_account_ids=payload.social_account_ids,
            platforms=legacy_platforms,
            stored_account_ids=list(content_job.target_social_account_ids or []),
        )
        if not accounts and legacy_platforms is None and detected_platforms:
            # Explicit empty stored ids + no request ids → fall back to asset platforms.
            accounts = await resolve_social_accounts(
                repo=self.repo,
                tenant_id=tenant_id,
                platforms=sorted(detected_platforms),
            )
        if not accounts:
            raise HTTPException(status_code=400, detail="No target social accounts available for publish")

        tenant_timezone = "UTC"
        try:
            from backend.modules.identity_access.repository import IdentityAccessRepository

            tenant = await IdentityAccessRepository(self.db).get_tenant_by_id(tenant_id)
            if tenant is not None and getattr(tenant, "timezone", None):
                tenant_timezone = str(tenant.timezone)
        except Exception:
            tenant_timezone = "UTC"

        scheduled_for_utc = (
            schedule_local_to_utc(payload.scheduled_for, tenant_timezone=tenant_timezone)
            if payload.scheduled_for
            else None
        )

        jobs: list[PublishingJob] = []
        new_jobs: list[PublishingJob] = []
        for social_account in accounts:
            platform = str(social_account.platform)
            idempotency_key = build_publish_idempotency_key(
                content_job_id=content_job.id,
                social_account_id=social_account.id,
                scheduled_for=scheduled_for_utc,
                dry_run=payload.dry_run,
                client_key=payload.idempotency_key,
            )
            existing = await self.repo.get_job_by_idempotency(idempotency_key)
            if existing:
                jobs.append(existing)
                continue
            connected_account = await self.repo.get_connected_for_social(tenant_id, social_account.id)
            if connected_account is None:
                connected_account = await self.repo.get_connected_account_by_platform(tenant_id, platform)
            provider = get_provider(
                platform,
                use_stub=social_account.account_metadata.get("mode") == "stub",
                access_token="",
                account_external_id=social_account.account_external_id or "",
                dry_run=payload.dry_run,
            )
            schedule_result = None
            if scheduled_for_utc:
                schedule_result = await provider.schedule_publish(
                    social_account=social_account,
                    assets=assets,
                    scheduled_for=scheduled_for_utc,
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
                    scheduled_for=scheduled_for_utc,
                    status=(
                        PublishingJobStatus.SCHEDULED.value
                        if scheduled_for_utc
                        else PublishingJobStatus.PENDING.value
                    ),
                    provider_payload={
                        "variant_fingerprint": variant_fingerprint(social_account),
                        "tenant_timezone": tenant_timezone,
                        "scheduled_for_utc": scheduled_for_utc.isoformat() if scheduled_for_utc else "",
                    },
                )
            )
            if schedule_result:
                job.provider_payload = {
                    **(job.provider_payload or {}),
                    **schedule_result.payload,
                    "native_scheduling_supported": str(schedule_result.native_supported).lower(),
                }
            jobs.append(job)
            new_jobs.append(job)

        if scheduled_for_utc is None:
            for job in new_jobs:
                # API path: commit attempt before I/O so crash mid-request is recoverable.
                await self._publish_job(tenant_id, job, commit_boundaries=True)
        await self.db.flush()
        return jobs

    async def execute_due_jobs(self, worker_id: str | None = None) -> list[PublishingJob]:
        """
        Claim (with lease), commit, then execute each job with attempt boundaries.
        """
        import uuid as _uuid

        effective_worker_id = worker_id or str(_uuid.uuid4())
        claimed = await self.repo.claim_due_jobs(worker_id=effective_worker_id)
        await self.db.commit()

        executed: list[PublishingJob] = []
        for job in claimed:
            try:
                executed.append(
                    await self._publish_job(
                        job.tenant_id,
                        job,
                        worker_id=effective_worker_id,
                        commit_boundaries=True,
                    )
                )
            except Exception:
                # Failure classification and job state already committed in _publish_job.
                continue
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
        job.claimed_at = None
        job.claim_expires_at = None
        job.worker_id = None
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
        latest = await self.repo.get_latest_attempt(job.id)
        if latest and latest.status == PublishingAttemptStatus.AMBIGUOUS.value:
            raise HTTPException(
                status_code=409,
                detail="Ambiguous attempt requires provider reconciliation before retry",
            )
        if job.social_account_id:
            account = await self.repo.get_social_account(tenant_id, job.social_account_id)
            if account is not None:
                retry_quota = await consume_retry_quota(tenant_id=tenant_id, account=account)
                if not retry_quota.allowed:
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "message": (
                                f"Account retry budget exhausted. Try again in "
                                f"{retry_quota.retry_after_seconds} seconds."
                            ),
                            "retry_after": retry_quota.retry_after_seconds,
                            "social_account_id": str(account.id),
                        },
                        headers={"Retry-After": str(retry_quota.retry_after_seconds)},
                    )
        job.status = PublishingJobStatus.PENDING.value
        job.failure_reason = None
        job.dead_letter_reason = None
        job.dead_lettered_at = None
        job.scheduled_for = None
        job.claimed_at = None
        job.claim_expires_at = None
        job.worker_id = None
        job.provider_payload = {
            **(job.provider_payload or {}),
            "retried_by_operator": "true",
        }
        await self.db.flush()
        return PublishingJobActionResponse(job_id=job.id, status=job.status, detail="Publishing job queued for retry")
