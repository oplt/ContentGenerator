from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership
from backend.api.deps.db import get_db
from backend.modules.audit.schemas import AuditLogResponse
from backend.modules.audit.service import AuditService
from backend.modules.identity_access.models import TenantUser

router = APIRouter()


@router.get("/logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    service = AuditService(db)
    logs = await service.list_logs(tenant_id=membership.tenant_id, limit=limit)
    return [AuditLogResponse.model_validate(log) for log in logs]
