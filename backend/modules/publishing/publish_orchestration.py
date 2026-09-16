from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from backend.modules.content_generation.variant_store import ContentVariantStore
from backend.modules.publishing.account_ops import consume_retry_quota, schedule_local_to_utc
from backend.modules.publishing.account_selection import (
    build_publish_idempotency_key,
    resolve_social_accounts,
    variant_fingerprint,
)
from backend.modules.publishing.models import (
    PublishingAttemptStatus,
    PublishingJob,
    PublishingJobStatus,
)
from backend.modules.publishing.providers import get_provider
from backend.modules.publishing.schemas import PublishNowRequest, PublishingJobActionResponse


async def publish_now(
    svc,
    *,
    tenant_id: UUID,
    approval_request_id: UUID | None,
    payload: PublishNowRequest,
) -> list[PublishingJob]:
    content_job = await svc.content_repo.get_job(tenant_id, payload.content_job_id)
    if not content_job:
        raise HTTPException(status_code=404, detail="Content job not found")
    assets = await svc.content_repo.list_assets(content_job.id)
    detected_platforms = {
        asset.platform
        for asset in assets
        if asset.platform and asset.asset_type == "text_variant"
    }
    legacy_platforms = payload.platforms or (
        None if (payload.social_account_ids or content_job.target_social_account_ids) else sorted(detected_platforms)
    )

    accounts = await resolve_social_accounts(
        repo=svc.repo,
        tenant_id=tenant_id,
        social_account_ids=payload.social_account_ids,
        platforms=legacy_platforms,
        stored_account_ids=list(content_job.target_social_account_ids or []),
    )
    if not accounts and legacy_platforms is None and detected_platforms:
        # Explicit empty stored ids + no request ids → fall back to asset platforms.
        accounts = await resolve_social_accounts(
            repo=svc.repo,
            tenant_id=tenant_id,
            platforms=sorted(detected_platforms),
        )
    if not accounts:
        raise HTTPException(status_code=400, detail="No target social accounts available for publish")

    tenant_timezone = "UTC"
    try:
        from backend.modules.identity_access.repository import IdentityAccessRepository

        tenant = await IdentityAccessRepository(svc.db).get_tenant_by_id(tenant_id)
        if tenant is not None and getattr(tenant, "timezone", None):
            tenant_timezone = str(tenant.timezone)
    except Exception:
        tenant_timezone = "UTC"

    scheduled_for_utc = (
        schedule_local_to_utc(payload.scheduled_for, tenant_timezone=tenant_timezone)
        if payload.scheduled_for
        else None
    )

    variant_store = ContentVariantStore(svc.db)
    preferred_variant_ids = list(payload.content_variant_ids or [])

    jobs: list[PublishingJob] = []
    new_jobs: list[PublishingJob] = []
    for social_account in accounts:
        platform = str(social_account.platform)
        variant_snap = await variant_store.resolve_for_account(
            tenant_id=tenant_id,
            content_job_id=content_job.id,
            social_account_id=social_account.id,
            preferred_variant_ids=preferred_variant_ids or None,
        )
        # When caller explicitly passed variant ids, require a match (no silent fallback).
        if preferred_variant_ids and variant_snap is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No ContentVariant among content_variant_ids targets "
                    f"social_account_id={social_account.id}"
                ),
            )

        content_variant_id = variant_snap.variant_id if variant_snap else None
        idempotency_key = build_publish_idempotency_key(
            content_job_id=content_job.id,
            social_account_id=social_account.id,
            scheduled_for=scheduled_for_utc,
            dry_run=payload.dry_run,
            client_key=payload.idempotency_key,
            content_variant_id=content_variant_id,
        )
        existing = await svc.repo.get_job_by_idempotency(idempotency_key)
        if existing:
            jobs.append(existing)
            continue
        connected_account = await svc.repo.get_connected_for_social(tenant_id, social_account.id)
        if connected_account is None:
            connected_account = await svc.repo.get_connected_account_by_platform(tenant_id, platform)
        provider = get_provider(
            platform,
            use_stub=social_account.account_metadata.get("mode") == "stub",
            access_token="",
            account_external_id=social_account.account_external_id or "",
            dry_run=payload.dry_run,
        )
        schedule_assets = assets
        if variant_snap is not None:
            from backend.modules.content_generation.variant_store import assets_from_variant_snapshot

            schedule_assets = assets_from_variant_snapshot(variant_snap, media_assets=assets)

        schedule_result = None
        if scheduled_for_utc:
            schedule_result = await provider.schedule_publish(
                social_account=social_account,
                assets=schedule_assets,
                scheduled_for=scheduled_for_utc,
            )

        provider_payload: dict[str, str] = {
            "variant_fingerprint": (
                variant_snap.fingerprint if variant_snap else variant_fingerprint(social_account)
            ),
            "tenant_timezone": tenant_timezone,
            "scheduled_for_utc": scheduled_for_utc.isoformat() if scheduled_for_utc else "",
        }
        if variant_snap is not None:
            provider_payload.update(variant_snap.as_provider_payload())

        job = await svc.repo.create_publishing_job(
            PublishingJob(
                tenant_id=tenant_id,
                content_job_id=content_job.id,
                content_variant_id=content_variant_id,
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
                provider_payload=provider_payload,
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
            await svc._publish_job(tenant_id, job, commit_boundaries=True)
    await svc.db.flush()
    return jobs


async def execute_due_jobs(svc, worker_id: str | None = None) -> list[PublishingJob]:
    """
    Claim (with lease), commit, then execute each job with attempt boundaries.
    """
    import uuid as _uuid

    effective_worker_id = worker_id or str(_uuid.uuid4())
    claimed = await svc.repo.claim_due_jobs(worker_id=effective_worker_id)
    await svc.db.commit()

    executed: list[PublishingJob] = []
    for job in claimed:
        try:
            executed.append(
                await svc._publish_job(
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


async def cancel_scheduled_job(svc, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
    job = await svc.repo.get_publishing_job(tenant_id, job_id)
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
    await svc.db.flush()
    return PublishingJobActionResponse(job_id=job.id, status=job.status, detail="Publishing job cancelled")


async def retry_job(svc, tenant_id: UUID, job_id: UUID) -> PublishingJobActionResponse:
    job = await svc.repo.get_publishing_job(tenant_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Publishing job not found")
    if job.status not in {
        PublishingJobStatus.FAILED.value,
        PublishingJobStatus.DEAD.value,
        PublishingJobStatus.CANCELLED.value,
        PublishingJobStatus.MANUAL_REQUIRED.value,
    }:
        raise HTTPException(status_code=409, detail="Only failed, dead-lettered, cancelled, or manual jobs can be retried")
    latest = await svc.repo.get_latest_attempt(job.id)
    if latest and latest.status == PublishingAttemptStatus.AMBIGUOUS.value:
        raise HTTPException(
            status_code=409,
            detail="Ambiguous attempt requires provider reconciliation before retry",
        )
    if job.social_account_id:
        account = await svc.repo.get_social_account(tenant_id, job.social_account_id)
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
    await svc.db.flush()
    return PublishingJobActionResponse(job_id=job.id, status=job.status, detail="Publishing job queued for retry")
