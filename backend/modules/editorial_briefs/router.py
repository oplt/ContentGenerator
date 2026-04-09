from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.editorial_briefs.schemas import (
    BriefApproveRequest,
    BriefGenerateRequest,
    BriefRejectRequest,
    BriefRewriteRequest,
    EditorialBriefResponse,
)
from backend.modules.editorial_briefs.service import EditorialBriefService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.post("", response_model=EditorialBriefResponse, status_code=201)
async def generate_brief(
    payload: BriefGenerateRequest,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    svc = EditorialBriefService(db)
    brief = await svc.generate_brief(
        membership.tenant_id,
        payload,
        actor_user_id=membership.user_id,
    )
    await db.commit()
    return EditorialBriefResponse.model_validate(brief)


@router.get("", response_model=list[EditorialBriefResponse])
async def list_briefs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[EditorialBriefResponse]:
    svc = EditorialBriefService(db)
    briefs = await svc.list_briefs(membership.tenant_id, status=status, limit=limit)
    return [EditorialBriefResponse.model_validate(b) for b in briefs]


@router.get("/{brief_id}", response_model=EditorialBriefResponse)
async def get_brief(
    brief_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    svc = EditorialBriefService(db)
    brief = await svc.get_brief(membership.tenant_id, brief_id)
    return EditorialBriefResponse.model_validate(brief)


@router.post("/{brief_id}/approve", response_model=EditorialBriefResponse)
async def approve_brief(
    brief_id: UUID,
    payload: BriefApproveRequest,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    svc = EditorialBriefService(db)
    brief = await svc.approve_brief(
        membership.tenant_id,
        brief_id,
        payload.operator_note,
        membership.user_id,
    )
    await db.commit()
    return EditorialBriefResponse.model_validate(brief)


@router.post("/{brief_id}/reject", response_model=EditorialBriefResponse)
async def reject_brief(
    brief_id: UUID,
    payload: BriefRejectRequest,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    svc = EditorialBriefService(db)
    brief = await svc.reject_brief(
        membership.tenant_id,
        brief_id,
        payload.operator_note,
        membership.user_id,
    )
    await db.commit()
    return EditorialBriefResponse.model_validate(brief)


@router.post("/{brief_id}/regenerate", response_model=EditorialBriefResponse)
async def regenerate_brief(
    brief_id: UUID,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    """Force-regenerate the LLM output for an existing brief (e.g. after rejection)."""
    svc = EditorialBriefService(db)
    brief = await svc.regenerate_brief(
        membership.tenant_id,
        brief_id,
        actor_user_id=membership.user_id,
    )
    await db.commit()
    return EditorialBriefResponse.model_validate(brief)


@router.post("/{brief_id}/rewrite", response_model=EditorialBriefResponse)
async def rewrite_brief(
    brief_id: UUID,
    payload: BriefRewriteRequest,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> EditorialBriefResponse:
    svc = EditorialBriefService(db)
    brief = await svc.rewrite_brief(
        membership.tenant_id,
        brief_id,
        payload,
        actor_user_id=membership.user_id,
    )
    await db.commit()
    return EditorialBriefResponse.model_validate(brief)


@router.post("/{brief_id}/send-telegram", status_code=200)
async def send_brief_to_telegram(
    brief_id: UUID,
    membership: TenantUser = Depends(require_permission("briefs:write")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send the editorial brief to Telegram for gate-1 topic approval."""
    svc = EditorialBriefService(db)
    result = await svc.send_to_telegram(membership.tenant_id, brief_id)
    await db.commit()
    return result
