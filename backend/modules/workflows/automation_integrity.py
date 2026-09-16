"""Automation brand / version / account integrity (Phase 6)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_strategy.models import Brand, BrandSocialAccount
from backend.modules.workflows.models import WorkflowVersion
from backend.modules.workflows.security import authorize_social_account_ids


async def require_active_brand(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    brand_id: UUID,
) -> Brand:
    """Brand must exist for tenant and not be soft-deleted."""
    result = await db.execute(
        select(Brand).where(
            Brand.tenant_id == tenant_id,
            Brand.id == brand_id,
            Brand.deleted_at.is_(None),
        )
    )
    brand = result.scalar_one_or_none()
    if brand is None:
        raise HTTPException(
            status_code=400,
            detail="Brand not found, deleted, or not in this tenant",
        )
    return brand


async def require_version_for_definition(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    workflow_definition_id: UUID,
    workflow_version_id: UUID,
    require_published: bool = True,
) -> WorkflowVersion:
    """Selected version must belong to the given definition (same tenant)."""
    result = await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.tenant_id == tenant_id,
            WorkflowVersion.id == workflow_version_id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=400, detail="Workflow version not found")
    if version.workflow_definition_id != workflow_definition_id:
        raise HTTPException(
            status_code=400,
            detail="Workflow version does not belong to the selected definition",
        )
    if require_published and version.published_at is None:
        raise HTTPException(status_code=400, detail="Workflow version is not published")
    return version


async def authorize_brand_linked_accounts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    brand_id: UUID,
    social_account_ids: list[UUID],
    allow_unlinked_targets: bool = False,
) -> None:
    """Targets must be tenant-authorized and linked to the automation brand.

    ``allow_unlinked_targets`` is an explicit admin override (default strict).
    """
    await authorize_social_account_ids(
        db, tenant_id=tenant_id, social_account_ids=social_account_ids
    )
    if not social_account_ids or allow_unlinked_targets:
        return

    result = await db.execute(
        select(BrandSocialAccount.social_account_id).where(
            BrandSocialAccount.tenant_id == tenant_id,
            BrandSocialAccount.brand_id == brand_id,
            BrandSocialAccount.social_account_id.in_(list(social_account_ids)),
            BrandSocialAccount.deleted_at.is_(None),
            BrandSocialAccount.enabled.is_(True),
        )
    )
    linked = {row for row in result.scalars().all()}
    missing = [str(aid) for aid in social_account_ids if aid not in linked]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Social accounts must be linked to the automation brand "
                    "via BrandSocialAccount (strict by default)"
                ),
                "unlinked_social_account_ids": missing,
                "brand_id": str(brand_id),
            },
        )
