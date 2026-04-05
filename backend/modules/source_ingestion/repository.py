from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.source_ingestion.models import RawArticle, Source, SourceFetchRun


class SourceRepository:
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

    async def list_due_sources(self) -> list[Source]:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(select(Source).where(Source.active.is_(True), Source.deleted_at.is_(None)))
        sources = list(result.scalars().all())
        return [
            source
            for source in sources
            if source.last_polled_at is None
            or source.last_polled_at <= now - timedelta(minutes=source.polling_interval_minutes)
        ]

    async def create_fetch_run(self, run: SourceFetchRun) -> SourceFetchRun:
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_existing_article(
        self, *, tenant_id: UUID, canonical_url: str, content_hash: str
    ) -> RawArticle | None:
        result = await self.db.execute(
            select(RawArticle).where(
                RawArticle.tenant_id == tenant_id,
                RawArticle.deleted_at.is_(None),
                or_(
                    RawArticle.canonical_url == canonical_url,
                    RawArticle.content_hash == content_hash,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def create_raw_article(self, article: RawArticle) -> RawArticle:
        self.db.add(article)
        await self.db.flush()
        return article

    async def list_raw_articles(self, *, tenant_id: UUID, limit: int = 100) -> list[RawArticle]:
        result = await self.db.execute(
            select(RawArticle)
            .where(RawArticle.tenant_id == tenant_id, RawArticle.deleted_at.is_(None))
            .order_by(RawArticle.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_fetch_runs(self, *, tenant_id: UUID, limit: int = 50) -> list[SourceFetchRun]:
        result = await self.db.execute(
            select(SourceFetchRun)
            .where(SourceFetchRun.tenant_id == tenant_id)
            .order_by(SourceFetchRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
