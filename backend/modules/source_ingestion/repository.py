from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.time_utils import utc_now
from backend.modules.source_ingestion.article_repository import (
    ArticleDedupeKeys,
    ArticleRepositoryMixin,
)
from backend.modules.source_ingestion.models import Source, SourceFetchRun, SourceHealthEvent

# Callers historically import ArticleDedupeKeys from this module.
__all__ = ("ArticleDedupeKeys", "SourceRepository")


class SourceRepository(ArticleRepositoryMixin):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_source(self, source: Source) -> Source:
        self.db.add(source)
        await self.db.flush()
        return source

    async def get_source(self, tenant_id: UUID, source_id: UUID) -> Source | None:
        result = await self.db.execute(
            select(Source).where(
                Source.id == source_id,
                Source.tenant_id == tenant_id,
                Source.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_sources(self, tenant_id: UUID) -> list[Source]:
        result = await self.db.execute(
            select(Source)
            .where(Source.tenant_id == tenant_id, Source.deleted_at.is_(None))
            .order_by(Source.created_at.desc())
        )
        return list(result.scalars().all())

    async def soft_delete_source(self, source: Source) -> None:
        source.active = False
        source.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def hard_delete_source(self, source: Source) -> None:
        await self.db.delete(source)
        await self.db.flush()

    async def list_due_sources(self, *, limit: int = 500) -> list[Source]:
        """Return active sources whose next_poll_at is due (SQL-filtered)."""
        now = utc_now()
        result = await self.db.execute(
            select(Source)
            .where(
                Source.active.is_(True),
                Source.deleted_at.is_(None),
                Source.next_poll_at.is_not(None),
                Source.next_poll_at <= now,
            )
            .order_by(Source.next_poll_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_fetch_run(self, run: SourceFetchRun) -> SourceFetchRun:
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_open_fetch_run(self, *, tenant_id: UUID, source_id: UUID) -> SourceFetchRun | None:
        result = await self.db.execute(
            select(SourceFetchRun)
            .where(
                SourceFetchRun.tenant_id == tenant_id,
                SourceFetchRun.source_id == source_id,
                SourceFetchRun.status.in_(
                    ("queued", "running"),
                ),
            )
            .order_by(SourceFetchRun.created_at.desc())
            .with_for_update()
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_fetch_run(
        self, *, tenant_id: UUID, source_id: UUID, fetch_run_id: UUID
    ) -> SourceFetchRun | None:
        result = await self.db.execute(
            select(SourceFetchRun).where(
                SourceFetchRun.id == fetch_run_id,
                SourceFetchRun.tenant_id == tenant_id,
                SourceFetchRun.source_id == source_id,
            ).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_fetch_run_for_tenant(
        self, *, tenant_id: UUID, fetch_run_id: UUID
    ) -> SourceFetchRun | None:
        result = await self.db.execute(
            select(SourceFetchRun).where(
                SourceFetchRun.id == fetch_run_id,
                SourceFetchRun.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_health_event(self, event: SourceHealthEvent) -> SourceHealthEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    # Article CRUD / dedupe lives on ArticleRepositoryMixin — do not re-declare here
    # (duplicate copies previously shadowed the mixin and broke imports like timedelta).

    async def list_fetch_runs(self, *, tenant_id: UUID, limit: int = 50) -> list[SourceFetchRun]:
        result = await self.db.execute(
            select(SourceFetchRun)
            .where(SourceFetchRun.tenant_id == tenant_id)
            .order_by(SourceFetchRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
