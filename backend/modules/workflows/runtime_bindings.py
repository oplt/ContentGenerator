"""Authorize manually supplied runtime bindings (Phase 8)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.automation_integrity import require_active_brand
from backend.modules.workflows.models import Automation
from backend.modules.workflows.security import authorize_social_account_ids


async def require_automation_for_tenant(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    automation_id: UUID,
) -> Automation:
    result = await db.execute(
        select(Automation).where(
            Automation.tenant_id == tenant_id,
            Automation.id == automation_id,
            Automation.deleted_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="Automation not found, deleted, or not in this tenant",
        )
    return row


async def authorize_runtime_bindings(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    automation_id: UUID | None = None,
    brand_id: UUID | None = None,
    social_account_ids: list[UUID] | None = None,
) -> None:
    """Ensure client-supplied automation/brand/account IDs are tenant-authorized."""
    automation: Automation | None = None
    if automation_id is not None:
        automation = await require_automation_for_tenant(
            db, tenant_id=tenant_id, automation_id=automation_id
        )
    if brand_id is not None:
        await require_active_brand(db, tenant_id=tenant_id, brand_id=brand_id)
        if automation is not None and automation.brand_id != brand_id:
            raise HTTPException(
                status_code=400,
                detail="brand_id does not match the selected automation brand",
            )
    if social_account_ids:
        await authorize_social_account_ids(
            db, tenant_id=tenant_id, social_account_ids=list(social_account_ids)
        )
