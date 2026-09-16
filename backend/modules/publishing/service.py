from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.service import AuditService
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.publishing.attempt_lifecycle import PublishAttemptLifecycle
from backend.modules.publishing.failure_classification import PublishErrorClass
from backend.modules.publishing.job_executor import publish_job
from backend.modules.publishing.models import (
    ConnectedAccount,
    PublishedPost,
    PublishingAttempt,
    PublishingJob,
    SocialAccount,
)
from backend.modules.publishing.publish_orchestration import (
    cancel_scheduled_job as _cancel_scheduled_job,
    execute_due_jobs as _execute_due_jobs,
    publish_now as _publish_now,
    retry_job as _retry_job,
)
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.publishing.schemas import (
    ConnectedAccountValidationResponse,
    PublishNowRequest,
    PublishingJobActionResponse,
    SocialAccountUpsertRequest,
)
from backend.modules.publishing.social_account_management import (
    upsert_social_account as _upsert_social_account,
    validate_connected_account as _validate_connected_account,
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

    async def upsert_social_account(
        self, tenant_id: UUID, payload: SocialAccountUpsertRequest, *, actor_user_id: UUID | None = None
    ) -> SocialAccount:
        return await _upsert_social_account(self, tenant_id, payload, actor_user_id=actor_user_id)

    async def validate_connected_account(
        self,
        tenant_id: UUID,
        connected_account_id: UUID,
    ) -> ConnectedAccountValidationResponse:
        return await _validate_connected_account(self, tenant_id, connected_account_id)

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
        return await _publish_now(
            self,
            tenant_id=tenant_id,
            approval_request_id=approval_request_id,
            payload=payload,
        )

    async def execute_due_jobs(self, worker_id: str | None = None) -> list[PublishingJob]:
        return await _execute_due_jobs(self, worker_id)

    async def list_jobs(self, tenant_id: UUID) -> list[PublishingJob]:
        return await self.repo.list_publishing_jobs(tenant_id)

    async def list_published_posts(self, tenant_id: UUID) -> list[PublishedPost]:
        return await self.repo.list_published_posts(tenant_id)

    async def cancel_scheduled_job(self, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
        return await _cancel_scheduled_job(self, tenant_id, job_id)

    async def retry_job(self, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
        return await _retry_job(self, tenant_id, job_id)
