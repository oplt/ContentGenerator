from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.publishing.schemas import (
    ConnectedAccountResponse,
    ConnectedAccountValidationResponse,
    PublishNowRequest,
    PublishedPostResponse,
    PublishingJobActionResponse,
    PublishingJobResponse,
    SocialAccountResponse,
    SocialAccountUpsertRequest,
)
from backend.modules.publishing.service import PublishingService

router = APIRouter()


def _job_response(job) -> PublishingJobResponse:
    payload = dict(job.provider_payload or {})
    recovery_actions = [
        item for item in str(payload.get("recovery_actions", "")).split(",") if item
    ]
    native_supported = str(payload.get("native_scheduling_supported", "false")).lower() == "true"
    return PublishingJobResponse(
        id=job.id,
        content_job_id=job.content_job_id,
        social_account_id=job.social_account_id,
        approval_request_id=job.approval_request_id,
        platform=str(job.platform),
        status=str(job.status),
        provider=job.provider,
        idempotency_key=job.idempotency_key,
        dry_run=job.dry_run,
        scheduled_for=job.scheduled_for,
        published_at=job.published_at,
        retry_count=job.retry_count,
        failure_reason=job.failure_reason,
        external_post_id=job.external_post_id,
        external_post_url=job.external_post_url,
        provider_payload=payload,
        recovery_actions=recovery_actions,
        native_scheduling_supported=native_supported,
    )


@router.get("/social-accounts", response_model=list[SocialAccountResponse])
async def list_social_accounts(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SocialAccountResponse]:
    service = PublishingService(db)
    return [
        SocialAccountResponse(
            id=account.id,
            platform=str(account.platform),
            display_name=account.display_name,
            handle=account.handle,
            account_external_id=account.account_external_id,
            status=str(account.status),
            capability_flags=account.capability_flags,
            metadata=account.account_metadata,
        )
        for account in await service.list_social_accounts(membership.tenant_id)
    ]


@router.post("/social-accounts", response_model=SocialAccountResponse, status_code=201)
async def upsert_social_account(
    payload: SocialAccountUpsertRequest,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> SocialAccountResponse:
    service = PublishingService(db)
    account = await service.upsert_social_account(membership.tenant_id, payload)
    await db.commit()
    return SocialAccountResponse(
        id=account.id,
        platform=str(account.platform),
        display_name=account.display_name,
        handle=account.handle,
        account_external_id=account.account_external_id,
        status=str(account.status),
        capability_flags=account.capability_flags,
        metadata=account.account_metadata,
    )


@router.get("/connected-accounts", response_model=list[ConnectedAccountResponse])
async def list_connected_accounts(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectedAccountResponse]:
    service = PublishingService(db)
    return [
        ConnectedAccountResponse(
            id=account.id,
            social_account_id=account.social_account_id,
            platform=str(account.platform),
            account_name=account.account_name,
            auth_type=account.auth_type,
            credential_ref=account.credential_ref,
            scopes=account.scopes,
            metadata=account.account_metadata,
            status=str(account.status),
        )
        for account in await service.list_connected_accounts(membership.tenant_id)
    ]


@router.post("/connected-accounts/{connected_account_id}/validate", response_model=ConnectedAccountValidationResponse)
async def validate_connected_account(
    connected_account_id: UUID,
    membership: TenantUser = Depends(require_permission("settings:write")),
    db: AsyncSession = Depends(get_db),
) -> ConnectedAccountValidationResponse:
    service = PublishingService(db)
    result = await service.validate_connected_account(membership.tenant_id, connected_account_id)
    await db.commit()
    return result


@router.get("/queue", response_model=list[PublishingJobResponse])
async def list_publishing_jobs(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[PublishingJobResponse]:
    service = PublishingService(db)
    return [_job_response(job) for job in await service.list_jobs(membership.tenant_id)]


@router.post("/publish-now", response_model=list[PublishingJobResponse])
async def publish_now(
    payload: PublishNowRequest,
    membership: TenantUser = Depends(require_permission("publishing:write")),
    db: AsyncSession = Depends(get_db),
) -> list[PublishingJobResponse]:
    service = PublishingService(db)
    jobs = await service.publish_now(
        tenant_id=membership.tenant_id,
        approval_request_id=None,
        payload=payload,
    )
    await db.commit()
    return [_job_response(job) for job in jobs]


@router.post("/queue/{job_id}/cancel", response_model=PublishingJobActionResponse)
async def cancel_scheduled_publish(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("publishing:write")),
    db: AsyncSession = Depends(get_db),
) -> PublishingJobActionResponse:
    service = PublishingService(db)
    result = await service.cancel_scheduled_job(membership.tenant_id, job_id)
    await db.commit()
    return result


@router.post("/queue/{job_id}/retry", response_model=PublishingJobActionResponse)
async def retry_publish_job(
    job_id: UUID,
    membership: TenantUser = Depends(require_permission("publishing:write")),
    db: AsyncSession = Depends(get_db),
) -> PublishingJobActionResponse:
    service = PublishingService(db)
    result = await service.retry_job(membership.tenant_id, job_id)
    await db.commit()
    return result


@router.get("/posts", response_model=list[PublishedPostResponse])
async def list_published_posts(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[PublishedPostResponse]:
    service = PublishingService(db)
    return [
        PublishedPostResponse.model_validate(post)
        for post in await service.list_published_posts(membership.tenant_id)
    ]
