from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.tenant_cache import OWNER_INGESTION, build_cache_key, tenant_cache
from backend.core.time_utils import utc_now
from backend.modules.audit.service import AuditService
from backend.modules.source_ingestion.adapters import (
    FetchedArticle,
    get_source_adapter,
)
from backend.modules.source_ingestion.models import (
    CircuitState,
    RawArticle,
    Source,
    SourceFetchRun,
    SourceHealthEvent,
)
from backend.modules.source_ingestion.pagination import decode_article_cursor, encode_article_cursor
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.source_ingestion.fetch_cache import (
    articles_from_cache,
    describe_fetch_error,
    save_cache,
    semantic_duplicate,
)
from backend.modules.source_ingestion.scheduling import compute_next_poll_at
from backend.modules.source_ingestion.schemas import (
    IngestionTriggerResponse,
    SourceActionResponse,
    SourceCreateRequest,
    SourceHealthResponse,
    SourceUpdateRequest,
)


class SourceIngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SourceRepository(db)
        self.audit = AuditService(db)

    @staticmethod
    def _recompute_trust_score(source: Source) -> float:
        """
        Blend the user-set baseline with observed reliability.
        baseline * 0.5 + consistency * 0.3 + longevity * 0.2
        consistency = success_count / (success_count + failure_count)
        longevity   = 1 - failure_rate (same denominator, inverse)
        """
        total = source.success_count + source.failure_count
        if total == 0:
            return source.trust_score
        consistency = source.success_count / total
        longevity = 1.0 - (source.failure_count / total)
        computed = (source.trust_score * 0.5) + (consistency * 0.3) + (longevity * 0.2)
        return round(min(max(computed, 0.0), 1.0), 4)

    async def create_source(self, tenant_id: UUID, payload: SourceCreateRequest) -> Source:
        data = payload.model_dump()
        now = utc_now()
        source = Source(
            tenant_id=tenant_id,
            **data,
            next_poll_at=compute_next_poll_at(
                last_polled_at=None,
                polling_interval_minutes=data.get("polling_interval_minutes", 30),
                now=now,
            ),
        )
        return await self.repo.create_source(source)

    async def update_source(self, tenant_id: UUID, source_id: UUID, payload: SourceUpdateRequest) -> Source:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        updates = payload.model_dump(exclude_none=True)
        for key, value in updates.items():
            setattr(source, key, value)
        if "polling_interval_minutes" in updates or source.next_poll_at is None:
            source.next_poll_at = compute_next_poll_at(
                last_polled_at=source.last_polled_at,
                polling_interval_minutes=source.polling_interval_minutes,
            )
        await self.db.flush()
        return source

    async def disable_source(self, tenant_id: UUID, source_id: UUID, reason: str = "disabled_by_operator") -> SourceActionResponse:
        source = await self.get_source(tenant_id, source_id)
        source.active = False
        source.disabled_reason = reason
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="ingestion.source_disabled",
            entity_type="source",
            entity_id=str(source.id),
            message=f"Source {source.name} disabled",
            payload={"reason": reason},
        )
        await self.db.flush()
        return SourceActionResponse(source_id=source.id, status="disabled", detail=reason)

    async def delete_source(self, tenant_id: UUID, source_id: UUID) -> None:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        await self.repo.hard_delete_source(source)
        await tenant_cache.delete(
            build_cache_key(
                owner=OWNER_INGESTION,
                tenant_id=source.tenant_id,
                identity=f"source:{source.id}:last_success",
            ),
            f"ingestion:source:{source.id}:last_success",
        )
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="ingestion.source_deleted",
            entity_type="source",
            entity_id=str(source.id),
            message=f"Source {source.name} deleted",
            payload={"source_type": str(source.source_type), "url": source.url},
        )
        await self.db.flush()

    async def list_sources(self, tenant_id: UUID) -> list[Source]:
        return await self.repo.list_sources(tenant_id)

    async def get_source(self, tenant_id: UUID, source_id: UUID) -> Source:
        source = await self.repo.get_source(tenant_id, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        return source

    async def list_raw_articles(
        self, tenant_id: UUID, *, limit: int = 100, cursor: str | None = None
    ) -> tuple[list[RawArticle], str | None, bool]:
        decoded = decode_article_cursor(cursor) if cursor else None
        articles = await self.repo.list_raw_articles(
            tenant_id=tenant_id,
            limit=limit + 1,
            cursor_created_at=decoded.created_at if decoded else None,
            cursor_id=decoded.article_id if decoded else None,
        )
        has_more = len(articles) > limit
        items = articles[:limit]
        next_cursor = None
        if has_more and items:
            next_cursor = encode_article_cursor(
                created_at=items[-1].created_at,
                article_id=items[-1].id,
            )
        return items, next_cursor, has_more

    async def list_fetch_runs(self, tenant_id: UUID) -> list[SourceFetchRun]:
        return await self.repo.list_fetch_runs(tenant_id=tenant_id)

    async def _record_health_event(
        self,
        *,
        source: Source,
        fetch_run: SourceFetchRun | None,
        status: str,
        event_type: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        await self.repo.create_health_event(
            SourceHealthEvent(
                tenant_id=source.tenant_id,
                source_id=source.id,
                fetch_run_id=fetch_run.id if fetch_run else None,
                status=status,
                event_type=event_type,
                message=message,
                details=details or {},
            )
        )

    async def source_health(self, tenant_id: UUID) -> list[SourceHealthResponse]:
        from backend.core.config import settings
        from backend.core.http import map_concurrent

        sources = await self.repo.list_sources(tenant_id)

        async def _check(source: Source) -> SourceHealthResponse:
            try:
                connector_health = await get_source_adapter(source).healthcheck()
                status = connector_health.get("status", "healthy")
            except Exception:
                status = "unhealthy"
            if source.circuit_state == CircuitState.OPEN.value and source.negative_cache_until:
                status = "degraded"
            elif not source.active:
                status = "paused"
            return SourceHealthResponse(
                source_id=source.id,
                status=status,
                failure_count=source.failure_count,
                success_count=source.success_count,
                circuit_state=source.circuit_state,
                negative_cache_until=source.negative_cache_until,
                last_success_at=source.last_success_at,
            )

        outcomes = await map_concurrent(
            sources,
            _check,
            limit=max(1, settings.HTTP_INGESTION_HEALTH_CONCURRENCY),
            return_exceptions=True,
        )
        health_items: list[SourceHealthResponse] = []
        for index, outcome in enumerate(outcomes):
            if isinstance(outcome, Exception):
                source = sources[index]
                health_items.append(
                    SourceHealthResponse(
                        source_id=source.id,
                        status="unhealthy",
                        failure_count=source.failure_count,
                        success_count=source.success_count,
                        circuit_state=source.circuit_state,
                        negative_cache_until=source.negative_cache_until,
                        last_success_at=source.last_success_at,
                    )
                )
            else:
                health_items.append(outcome)
        return health_items

    def _semantic_duplicate(
        self,
        candidate: FetchedArticle,
        recent_articles: list[RawArticle],
        *,
        token_index: list[tuple[RawArticle, frozenset[str]]] | None = None,
    ) -> RawArticle | None:
        return semantic_duplicate(candidate, recent_articles, token_index=token_index)

    async def _articles_from_cache(self, source: Source) -> list[FetchedArticle]:
        return await articles_from_cache(source)

    async def _save_cache(self, source: Source, articles: list[FetchedArticle]) -> None:
        await save_cache(source, articles)

    def _describe_fetch_error(self, exc: Exception) -> str:
        return describe_fetch_error(exc)

    async def run_ingestion(self, tenant_id: UUID, source_id: UUID) -> IngestionTriggerResponse:
        """Delegate to split-phase workflow (no DB hold across network I/O)."""
        from backend.modules.source_ingestion.ingestion_workflow import run_ingestion_workflow

        return await run_ingestion_workflow(tenant_id=tenant_id, source_id=source_id)

    async def trigger_manual_poll(self, tenant_id: UUID, source_id: UUID) -> IngestionTriggerResponse:
        return await self.run_ingestion(tenant_id, source_id)

    async def poll_due_sources(self) -> list[IngestionTriggerResponse]:
        import structlog

        log = structlog.get_logger(__name__)
        from backend.modules.source_ingestion.ingestion_workflow import run_ingestion_workflow

        results: list[IngestionTriggerResponse] = []
        due = await self.repo.list_due_sources()
        for source in due:
            try:
                results.append(
                    await run_ingestion_workflow(tenant_id=source.tenant_id, source_id=source.id)
                )
            except Exception:
                log.exception(
                    "source_poll_failed", source_id=str(source.id), tenant_id=str(source.tenant_id)
                )
        return results
