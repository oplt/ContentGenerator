from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.publishing.schemas import PublishNowRequest, PublishedPostResponse, PublishingJobResponse, SocialAccountResponse, SocialAccountUpsertRequest
from backend.modules.publishing.service import PublishingService

router = APIRouter()


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


@router.get("/queue", response_model=list[PublishingJobResponse])
async def list_publishing_jobs(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[PublishingJobResponse]:
    service = PublishingService(db)
    return [
        PublishingJobResponse.model_validate(job)
        for job in await service.list_jobs(membership.tenant_id)
    ]


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
    return [PublishingJobResponse.model_validate(job) for job in jobs]


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
