from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_membership, require_permission
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import TenantUser
from backend.modules.source_ingestion.catalog import CATALOG, CATALOG_BY_ID
from backend.modules.source_ingestion.schemas import (
    CatalogEntryResponse,
    RawArticlePageResponse,
    IngestionTriggerResponse,
    RawArticleResponse,
    SourceActionResponse,
    SourceCreateRequest,
    SourceFetchRunResponse,
    SourceHealthResponse,
    SourceResponse,
    SourceUpdateRequest,
)
from backend.modules.source_ingestion.service import SourceIngestionService

router = APIRouter()


async def _enqueue_source_ingestion(
    *, source_id: UUID, membership: TenantUser, db: AsyncSession, correlation_id: str | None
) -> IngestionTriggerResponse:
    service = SourceIngestionService(db)
    fetch_run, created = await service.queue_ingestion(
        membership.tenant_id,
        source_id,
        correlation_id=correlation_id,
    )
    metadata = fetch_run.fetch_metadata or {}
    task_id = metadata.get("celery_task_id")
    task_id = task_id if isinstance(task_id, str) else ""
    if created:
        from backend.workers.tasks import ingest_source_task

        await db.commit()
        try:
            ingest_source_task.apply_async(
                kwargs={
                    "tenant_id": str(membership.tenant_id),
                    "source_id": str(source_id),
                    "fetch_run_id": str(fetch_run.id),
                    "correlation_id": correlation_id,
                },
                task_id=task_id,
                headers={"correlation_id": correlation_id} if correlation_id else None,
            )
        except Exception as exc:
            fetch_run.status = "failed"
            fetch_run.error_message = "Unable to enqueue ingestion task"
            await db.commit()
            raise HTTPException(status_code=503, detail="Ingestion queue unavailable") from exc
    return IngestionTriggerResponse(
        source_id=source_id,
        status="queued" if created else fetch_run.status,
        raw_articles_ingested=0,
        clusters_updated=0,
        fetch_run_id=fetch_run.id,
        task_id=task_id or None,
    )


def _fetch_run_response(run) -> SourceFetchRunResponse:
    meta = run.fetch_metadata or {}
    celery_task_id = meta.get("celery_task_id")
    correlation_id = meta.get("correlation_id")
    base = SourceFetchRunResponse.model_validate(run)
    return base.model_copy(
        update={
            "celery_task_id": celery_task_id if isinstance(celery_task_id, str) else None,
            "correlation_id": correlation_id if isinstance(correlation_id, str) else None,
        }
    )


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
    return SourceResponse.model_validate(source)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: UUID,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    service = SourceIngestionService(db)
    await service.delete_source(membership.tenant_id, source_id)
    return Response(status_code=204)


@router.post("/{source_id}/disable", response_model=SourceActionResponse)
async def disable_source(
    source_id: UUID,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> SourceActionResponse:
    service = SourceIngestionService(db)
    result = await service.disable_source(membership.tenant_id, source_id)
    return result


@router.post("/{source_id}/ingest", response_model=IngestionTriggerResponse, status_code=202)
async def ingest_source(
    source_id: UUID,
    request: Request,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> IngestionTriggerResponse:
    return await _enqueue_source_ingestion(
        source_id=source_id,
        membership=membership,
        db=db,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


@router.post("/{source_id}/manual-poll", response_model=IngestionTriggerResponse)
async def manual_poll_source(
    source_id: UUID,
    request: Request,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> IngestionTriggerResponse:
    return await _enqueue_source_ingestion(
        source_id=source_id,
        membership=membership,
        db=db,
        correlation_id=getattr(request.state, "correlation_id", None),
    )


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
    return [_fetch_run_response(run) for run in await service.list_fetch_runs(membership.tenant_id)]


@router.get("/fetch-runs/{fetch_run_id}", response_model=SourceFetchRunResponse)
async def get_fetch_run(
    fetch_run_id: UUID,
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> SourceFetchRunResponse:
    service = SourceIngestionService(db)
    run = await service.repo.get_fetch_run_for_tenant(
        tenant_id=membership.tenant_id,
        fetch_run_id=fetch_run_id,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return _fetch_run_response(run)


@router.get("/catalog", response_model=list[CatalogEntryResponse])
async def list_catalog(
    category: str | None = Query(default=None),
    membership: TenantUser = Depends(get_current_membership),
) -> list[CatalogEntryResponse]:
    entries = CATALOG if category is None else [e for e in CATALOG if e["category"] == category]
    return [
        CatalogEntryResponse(
            id=e["id"],
            name=e["name"],
            url=e["url"],
            source_type=e["source_type"],
            category=e["category"],
            description=e["description"],
            trust_score=e["trust_score"],
            polling_interval_minutes=e["polling_interval_minutes"],
        )
        for e in entries
    ]


@router.post("/catalog/{catalog_id}/import", response_model=SourceResponse, status_code=201)
async def import_catalog_source(
    catalog_id: str,
    membership: TenantUser = Depends(require_permission("sources:write")),
    db: AsyncSession = Depends(get_db),
) -> SourceResponse:
    from fastapi import HTTPException as _HTTPException
    entry = CATALOG_BY_ID.get(catalog_id)
    if not entry:
        raise _HTTPException(status_code=404, detail="Catalog entry not found")
    service = SourceIngestionService(db)
    config: dict[str, str] = {}
    if entry.get("fetch_full_text"):
        config["fetch_full_text"] = "true"
    payload = SourceCreateRequest(
        name=entry["name"],
        source_type=entry["source_type"],
        url=entry["url"],
        parser_type="auto",
        category=entry["category"],
        trust_score=entry["trust_score"],
        polling_interval_minutes=entry["polling_interval_minutes"],
        config=config,
        active=True,
    )
    source = await service.create_source(membership.tenant_id, payload)
    return SourceResponse.model_validate(source)


@router.get("/articles", response_model=RawArticlePageResponse)
async def list_raw_articles(
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None),
    membership: TenantUser = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> RawArticlePageResponse:
    service = SourceIngestionService(db)
    try:
        articles, next_cursor, has_more = await service.list_raw_articles(
            membership.tenant_id, limit=limit, cursor=cursor
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RawArticlePageResponse(
        items=[RawArticleResponse.model_validate(article) for article in articles],
        next_cursor=next_cursor,
        has_more=has_more,
    )
