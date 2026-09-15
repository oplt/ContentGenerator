"""Publishing job claim / stale-lease recovery (set-based, bounded batches)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics
from backend.core.log_context import bind_log_context
from backend.modules.publishing.models import (
    PublishingAttempt,
    PublishingAttemptStatus,
    PublishingJob,
    PublishingJobStatus,
)


class JobClaimingMixin:
    db: AsyncSession

    async def get_latest_attempt(self, publishing_job_id: UUID) -> PublishingAttempt | None:
        latest = await self.get_latest_attempts_for_jobs([publishing_job_id])
        return latest.get(publishing_job_id)

    async def get_latest_attempts_for_jobs(
        self, publishing_job_ids: list[UUID]
    ) -> dict[UUID, PublishingAttempt]:
        """Latest attempt per job via DISTINCT ON (one query, not N+1)."""
        if not publishing_job_ids:
            return {}
        result = await self.db.execute(
            select(PublishingAttempt)
            .where(PublishingAttempt.publishing_job_id.in_(publishing_job_ids))
            .distinct(PublishingAttempt.publishing_job_id)
            .order_by(
                PublishingAttempt.publishing_job_id,
                PublishingAttempt.attempt_number.desc(),
            )
        )
        return {attempt.publishing_job_id: attempt for attempt in result.scalars().all()}

    async def claim_due_jobs(
        self,
        worker_id: str,
        batch_size: int | None = None,
        lease_seconds: int | None = None,
    ) -> list[PublishingJob]:
        """
        Atomically claim due jobs and recover expired leases.

        Uses SELECT ... FOR UPDATE SKIP LOCKED. Sets claim_expires_at lease.
        Returns claimed jobs (status CLAIMED). Caller must commit before I/O.
        """
        now = datetime.now(timezone.utc)
        size = batch_size or settings.PUBLISHING_CLAIM_BATCH_SIZE
        lease = lease_seconds or settings.PUBLISHING_CLAIM_LEASE_SECONDS
        claim_expires_at = now + timedelta(seconds=lease)

        await self._recover_stale_claims(now=now, batch_size=size)

        due_status = [PublishingJobStatus.PENDING.value, PublishingJobStatus.SCHEDULED.value]
        subq = (
            select(PublishingJob.id)
            .where(
                PublishingJob.status.in_(due_status),
                or_(
                    PublishingJob.scheduled_for.is_(None),
                    PublishingJob.scheduled_for <= now,
                ),
                or_(
                    PublishingJob.claimed_at.is_(None),
                    PublishingJob.claim_expires_at.is_(None),
                    PublishingJob.claim_expires_at <= now,
                ),
            )
            .order_by(PublishingJob.scheduled_for.asc().nullsfirst(), PublishingJob.created_at.asc())
            .limit(size)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(subq)
        job_ids = [row[0] for row in result.fetchall()]
        if not job_ids:
            return []

        claimed = await self.db.execute(
            update(PublishingJob)
            .where(PublishingJob.id.in_(job_ids))
            .values(
                status=PublishingJobStatus.CLAIMED.value,
                claimed_at=now,
                claim_expires_at=claim_expires_at,
                worker_id=worker_id,
            )
            .returning(PublishingJob)
        )
        await self.db.flush()
        jobs = list(claimed.scalars().all())
        domain_metrics.record_publish_claim(event="claimed", amount=len(jobs))
        if jobs:
            bind_log_context(publishing_job_id=jobs[0].id, stage="claim")
        return jobs

    async def _recover_stale_claims(self, *, now: datetime, batch_size: int) -> int:
        """Release or escalate jobs whose claim lease expired mid-flight."""
        stale_result = await self.db.execute(
            select(PublishingJob)
            .where(
                PublishingJob.status.in_(
                    [
                        PublishingJobStatus.CLAIMED.value,
                        PublishingJobStatus.RUNNING.value,
                    ]
                ),
                PublishingJob.claim_expires_at.is_not(None),
                PublishingJob.claim_expires_at <= now,
            )
            .order_by(PublishingJob.claim_expires_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        stale_jobs = list(stale_result.scalars().all())
        if not stale_jobs:
            return 0

        latest_by_job = await self.get_latest_attempts_for_jobs([job.id for job in stale_jobs])
        recovered = 0
        for job in stale_jobs:
            latest = latest_by_job.get(job.id)
            if latest and latest.status == PublishingAttemptStatus.SUCCEEDED.value:
                if job.status not in {
                    PublishingJobStatus.SUCCEEDED.value,
                    PublishingJobStatus.SUCCEEDED_DRY_RUN.value,
                }:
                    job.status = PublishingJobStatus.MANUAL_REQUIRED.value
                    job.failure_reason = "stale_claim_after_provider_success"
                    job.claimed_at = None
                    job.claim_expires_at = None
                    job.worker_id = None
                    job.provider_payload = {
                        **(job.provider_payload or {}),
                        "recovery_actions": "reconcile_provider_post,manual_finalize",
                        "stale_claim_recovery": "manual_required_after_success",
                    }
                    recovered += 1
                continue

            if latest and latest.status == PublishingAttemptStatus.AMBIGUOUS.value:
                job.status = PublishingJobStatus.MANUAL_REQUIRED.value
                job.failure_reason = latest.error_message or "stale_claim_ambiguous_attempt"
                job.claimed_at = None
                job.claim_expires_at = None
                job.worker_id = None
                job.provider_payload = {
                    **(job.provider_payload or {}),
                    "recovery_actions": (
                        "reconcile_provider_post,manual_delete_if_duplicate,retry_publish"
                    ),
                    "stale_claim_recovery": "manual_required_ambiguous",
                }
                recovered += 1
                continue

            job.status = PublishingJobStatus.SCHEDULED.value
            job.scheduled_for = now
            job.claimed_at = None
            job.claim_expires_at = None
            job.worker_id = None
            job.provider_payload = {
                **(job.provider_payload or {}),
                "stale_claim_recovery": "requeued",
                "recovered_at": now.isoformat(),
            }
            recovered += 1
        if recovered:
            await self.db.flush()
            domain_metrics.record_publish_claim(event="recovered", amount=recovered)
        return recovered
