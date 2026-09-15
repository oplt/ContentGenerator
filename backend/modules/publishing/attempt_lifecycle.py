from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics
from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.account_ops import build_account_display_snapshot
from backend.modules.publishing.failure_classification import PublishErrorClass
from backend.modules.publishing.models import (
    PublishedPost,
    PublishedPostStatus,
    PublishingAttempt,
    PublishingAttemptStatus,
    PublishingJob,
    PublishingJobStatus,
    SocialAccount,
)
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.story_intelligence.models import TrendWorkflowState
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository


class PublishAttemptLifecycle:
    """Durable prepare/finalize boundaries for publishing attempts."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: PublishingRepository,
        content_repo: ContentGenerationRepository,
        story_repo: StoryIntelligenceRepository,
        audit: AuditService,
    ) -> None:
        self.db = db
        self.repo = repo
        self.content_repo = content_repo
        self.story_repo = story_repo
        self.audit = audit

    @staticmethod
    def build_recovery_actions(platform: str, failure_reason: str | None = None) -> list[str]:
        actions = ["retry_publish", "open_manual_publish_runbook", "reauthorize_account"]
        if failure_reason:
            actions.append(f"review_failure:{failure_reason[:80]}")
        if platform in {"x", "bluesky"}:
            actions.append("manual_delete_if_duplicate")
        return actions

    @staticmethod
    def build_attempt_key(job: PublishingJob, attempt_number: int) -> str:
        return f"{job.idempotency_key}:attempt:{attempt_number}"

    async def prepare_attempt(
        self,
        job: PublishingJob,
        *,
        worker_id: str | None,
    ) -> PublishingAttempt:
        existing_post = await self.repo.get_published_post_for_job(job.id)
        if existing_post:
            raise HTTPException(status_code=409, detail="Publishing job already has a published post")

        attempt_number = (job.retry_count or 0) + 1
        attempt_key = self.build_attempt_key(job, attempt_number)
        existing_attempt = await self.repo.get_attempt_by_key(attempt_key)
        now = datetime.now(timezone.utc)
        if existing_attempt:
            if existing_attempt.status == PublishingAttemptStatus.SUCCEEDED.value:
                raise HTTPException(status_code=409, detail="Publish attempt already succeeded")
            if existing_attempt.status == PublishingAttemptStatus.AMBIGUOUS.value:
                raise HTTPException(
                    status_code=409,
                    detail="Previous attempt is ambiguous; reconcile before retrying",
                )
            attempt = existing_attempt
            attempt.status = PublishingAttemptStatus.PREPARED.value
            attempt.worker_id = worker_id
            attempt.started_at = now
            attempt.finished_at = None
            attempt.error_class = None
            attempt.error_message = None
        else:
            attempt = await self.repo.create_attempt(
                PublishingAttempt(
                    publishing_job_id=job.id,
                    attempt_number=attempt_number,
                    attempt_key=attempt_key,
                    status=PublishingAttemptStatus.PREPARED.value,
                    worker_id=worker_id,
                    started_at=now,
                    provider_payload={},
                )
            )

        job.status = PublishingJobStatus.RUNNING.value
        job.current_attempt_key = attempt.attempt_key
        job.claimed_at = job.claimed_at or now
        job.claim_expires_at = now + timedelta(seconds=settings.PUBLISHING_CLAIM_LEASE_SECONDS)
        if worker_id:
            job.worker_id = worker_id
        await self.db.flush()
        return attempt

    async def finalize_success(
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
        now = datetime.now(timezone.utc)
        if result.manual_required:
            job.status = PublishingJobStatus.MANUAL_REQUIRED.value
        elif result.status == PublishingJobStatus.SUCCEEDED_DRY_RUN.value:
            job.status = PublishingJobStatus.SUCCEEDED_DRY_RUN.value
        else:
            job.status = PublishingJobStatus.SUCCEEDED.value
        job.published_at = now
        job.external_post_id = result.external_post_id
        job.external_post_url = result.external_post_url
        job.claimed_at = None
        job.claim_expires_at = None
        job.worker_id = None
        job.failure_reason = None
        job.provider = getattr(result, "provider", None) or job.provider
        job.provider_payload = {
            **result.payload,
            "draft_preview": draft_preview,
            "draft_status": draft_status,
            "publish_attempt_key": publish_attempt_key,
            "auth_status": auth_status,
            "recovery_actions": ",".join(self.build_recovery_actions(job.platform)),
        }

        attempt.status = PublishingAttemptStatus.SUCCEEDED.value
        attempt.finished_at = now
        attempt.external_post_id = result.external_post_id
        attempt.external_post_url = result.external_post_url
        attempt.provider_payload = dict(result.payload)

        existing_post = await self.repo.get_published_post_for_job(job.id)
        if not existing_post:
            await self.repo.create_published_post(
                PublishedPost(
                    tenant_id=tenant_id,
                    social_account_id=social_account.id,
                    publishing_job_id=job.id,
                    platform=job.platform,
                    post_type=post_type,
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
                    account_display_snapshot=build_account_display_snapshot(social_account),
                )
            )

        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="publishing.job_executed",
            entity_type="publishing_job",
            entity_id=str(job.id),
            message="Publishing job executed",
            payload={"platform": job.platform, "status": job.status, "attempt_key": publish_attempt_key},
        )
        content_job = await self.content_repo.get_job(tenant_id, job.content_job_id)
        if content_job:
            from backend.modules.content_strategy.repository import ContentStrategyRepository

            plan = await ContentStrategyRepository(self.db).get_content_plan(
                tenant_id, content_job.content_plan_id
            )
            if plan:
                cluster = await self.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
                if cluster:
                    cluster.workflow_state = TrendWorkflowState.PUBLISHED.value
        await self.db.flush()
        domain_metrics.record_publish_attempt(
            platform=str(job.platform or "unknown"),
            outcome="success",
            post_type=post_type,
        )
        return job

    async def finalize_failure(
        self,
        *,
        job: PublishingJob,
        attempt: PublishingAttempt,
        exc: BaseException,
        error_class: PublishErrorClass,
    ) -> None:
        now = datetime.now(timezone.utc)
        message = str(exc)[:500]
        job.failure_reason = message
        job.retry_count = max(job.retry_count or 0, attempt.attempt_number)
        job.claimed_at = None
        job.claim_expires_at = None
        job.worker_id = None
        attempt.finished_at = now
        attempt.error_class = error_class.value
        attempt.error_message = message

        if error_class == PublishErrorClass.AMBIGUOUS:
            attempt.status = PublishingAttemptStatus.AMBIGUOUS.value
            job.status = PublishingJobStatus.MANUAL_REQUIRED.value
            job.provider_payload = {
                **(job.provider_payload or {}),
                "recovery_actions": ",".join(
                    self.build_recovery_actions(job.platform, message)
                    + ["reconcile_provider_post"]
                ),
                "error_class": error_class.value,
                "attempt_key": attempt.attempt_key,
            }
        elif error_class == PublishErrorClass.PERMANENT or attempt.attempt_number >= settings.PUBLISHING_MAX_ATTEMPTS:
            attempt.status = (
                PublishingAttemptStatus.FAILED_PERMANENT.value
                if error_class == PublishErrorClass.PERMANENT
                else PublishingAttemptStatus.FAILED_TRANSIENT.value
            )
            job.status = PublishingJobStatus.DEAD.value
            job.dead_lettered_at = now
            job.dead_letter_reason = message
            job.provider_payload = {
                **(job.provider_payload or {}),
                "recovery_actions": ",".join(self.build_recovery_actions(job.platform, message)),
                "dead_letter": "true",
                "error_class": error_class.value,
                "attempt_key": attempt.attempt_key,
            }
            await self.audit.record(
                tenant_id=job.tenant_id,
                actor_user_id=None,
                action="publishing.dead_lettered",
                entity_type="publishing_job",
                entity_id=str(job.id),
                message="Publishing job moved to dead-letter state",
                payload={"platform": job.platform, "failure_reason": message, "error_class": error_class.value},
                severity="warning",
                outcome="dead_lettered",
                payload_schema="publishing.dead_letter.v1",
            )
        else:
            attempt.status = PublishingAttemptStatus.FAILED_TRANSIENT.value
            backoff_minutes = 2 ** attempt.attempt_number
            job.status = PublishingJobStatus.SCHEDULED.value
            job.scheduled_for = now + timedelta(minutes=backoff_minutes)
            job.provider_payload = {
                **(job.provider_payload or {}),
                "recovery_actions": ",".join(self.build_recovery_actions(job.platform, message)),
                "next_retry_at": job.scheduled_for.isoformat(),
                "backoff_minutes": str(backoff_minutes),
                "error_class": error_class.value,
                "attempt_key": attempt.attempt_key,
            }
        await self.db.flush()
        domain_metrics.record_publish_attempt(
            platform=str(job.platform or "unknown"),
            outcome=attempt.status or "failed",
            error_class=error_class.value,
        )
