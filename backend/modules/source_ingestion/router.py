from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.source_ingestion.schemas import (
    IngestionTriggerResponse,
    RawArticleResponse,
    SourceCreateRequest,
    SourceFetchRunResponse,
    SourceHealthResponse,
    SourceResponse,
    SourceUpdateRequest,
)
from backend.modules.source_ingestion.service import SourceIngestionService

router = APIRouter()


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SourceResponse]:
    service = SourceIngestionService(db)
    return [SourceResponse.model_validate(source) for source in await service.list_sources(membership.tenant_id)]


@router.post("", response_model=SourceResponse, status_code=201)
async def create_source(
    payload: SourceCreateRequest,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> SourceResponse:
    service = SourceIngestionService(db)
    source = await service.create_source(membership.tenant_id, payload)
    await db.commit()
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: UUID,
    payload: SourceUpdateRequest,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> SourceResponse:
    service = SourceIngestionService(db)
    source = await service.update_source(membership.tenant_id, source_id, payload)
    await db.commit()
    return SourceResponse.model_validate(source)


@router.post("/{source_id}/ingest", response_model=IngestionTriggerResponse)
async def ingest_source(
    source_id: UUID,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> IngestionTriggerResponse:
    service = SourceIngestionService(db)
    return await service.run_ingestion(membership.tenant_id, source_id)


@router.get("/health", response_model=list[SourceHealthResponse])
async def source_health(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SourceHealthResponse]:
    service = SourceIngestionService(db)
    return await service.source_health(membership.tenant_id)


@router.get("/fetch-runs", response_model=list[SourceFetchRunResponse])
async def list_fetch_runs(
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[SourceFetchRunResponse]:
    service = SourceIngestionService(db)
    return [
        SourceFetchRunResponse.model_validate(run)
        for run in await service.list_fetch_runs(membership.tenant_id)
    ]


@router.get("/articles", response_model=list[RawArticleResponse])
async def list_raw_articles(
    limit: int = Query(default=100, ge=1, le=500),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> list[RawArticleResponse]:
    service = SourceIngestionService(db)
    return [
        RawArticleResponse.model_validate(article)
        for article in (await service.list_raw_articles(membership.tenant_id))[:limit]
    ]
