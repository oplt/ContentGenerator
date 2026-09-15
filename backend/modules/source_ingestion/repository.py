from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.time_utils import utc_now
from backend.modules.source_ingestion.models import RawArticle, Source, SourceFetchRun, SourceHealthEvent


@dataclass(frozen=True, slots=True)
class ArticleDedupeKeys:
    canonical_url: str
    content_hash: str
    dedupe_key: str | None = None
    title_normalized: str | None = None


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

    async def create_health_event(self, event: SourceHealthEvent) -> SourceHealthEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def get_existing_article(
        self,
        *,
        tenant_id: UUID,
        canonical_url: str,
        content_hash: str,
        dedupe_key: str | None = None,
        title_normalized: str | None = None,
    ) -> RawArticle | None:
        matches = await self.find_existing_articles_batch(
            tenant_id=tenant_id,
            candidates=[
                ArticleDedupeKeys(
                    canonical_url=canonical_url,
                    content_hash=content_hash,
                    dedupe_key=dedupe_key,
                    title_normalized=title_normalized,
                )
            ],
        )
        return matches.get(0)

    @staticmethod
    def _article_matches_keys(article: RawArticle, keys: ArticleDedupeKeys) -> bool:
        if article.content_hash == keys.content_hash:
            return True
        if article.canonical_url == keys.canonical_url:
            return True
        if keys.dedupe_key and article.dedupe_key == keys.dedupe_key:
            return True
        if keys.title_normalized and article.title_normalized == keys.title_normalized:
            return True
        return False

    async def find_existing_articles_batch(
        self,
        *,
        tenant_id: UUID,
        candidates: list[ArticleDedupeKeys],
    ) -> dict[int, RawArticle]:
        """
        One tenant-scoped query for all candidate key collisions.

        Returns mapping of candidate index -> first matching RawArticle.
        Query count is O(1) relative to candidate count.
        """
        if not candidates:
            return {}

        content_hashes = {item.content_hash for item in candidates if item.content_hash}
        canonical_urls = {item.canonical_url for item in candidates if item.canonical_url}
        dedupe_keys = {item.dedupe_key for item in candidates if item.dedupe_key}
        titles = {item.title_normalized for item in candidates if item.title_normalized}

        key_filters = []
        if content_hashes:
            key_filters.append(RawArticle.content_hash.in_(content_hashes))
        if canonical_urls:
            key_filters.append(RawArticle.canonical_url.in_(canonical_urls))
        if dedupe_keys:
            key_filters.append(RawArticle.dedupe_key.in_(dedupe_keys))
        if titles:
            key_filters.append(RawArticle.title_normalized.in_(titles))
        if not key_filters:
            return {}

        result = await self.db.execute(
            select(RawArticle).where(
                RawArticle.tenant_id == tenant_id,
                RawArticle.deleted_at.is_(None),
                or_(*key_filters),
            )
        )
        existing_rows = list(result.scalars().all())
        matches: dict[int, RawArticle] = {}
        for index, keys in enumerate(candidates):
            for article in existing_rows:
                if self._article_matches_keys(article, keys):
                    matches[index] = article
                    break
        return matches

    async def list_recent_raw_articles(
        self,
        *,
        tenant_id: UUID,
        within_hours: int = 24,
        limit: int = 200,
    ) -> list[RawArticle]:
        since = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        result = await self.db.execute(
            select(RawArticle)
            .where(
                RawArticle.tenant_id == tenant_id,
                RawArticle.deleted_at.is_(None),
                RawArticle.created_at >= since,
            )
            .order_by(RawArticle.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_raw_article(self, article: RawArticle) -> RawArticle:
        self.db.add(article)
        await self.db.flush()
        return article

    async def insert_raw_article_conflict_safe(self, article: RawArticle) -> RawArticle | None:
        """
        Insert article; on (tenant_id, content_hash) conflict return None.

        Preserves race safety when concurrent workers ingest the same hash.
        """
        article_id = article.id or uuid4()
        article.id = article_id
        stmt = (
            insert(RawArticle)
            .values(
                id=article_id,
                tenant_id=article.tenant_id,
                source_id=article.source_id,
                fetch_run_id=article.fetch_run_id,
                url=article.url,
                canonical_url=article.canonical_url,
                dedupe_key=article.dedupe_key,
                title_normalized=article.title_normalized,
                content_hash=article.content_hash,
                title=article.title,
                summary=article.summary,
                body=article.body,
                author=article.author,
                language=article.language,
                published_at=article.published_at,
                extraction_confidence=article.extraction_confidence,
                source_metadata=article.source_metadata or {},
                deleted_at=article.deleted_at,
            )
            .on_conflict_do_nothing(constraint="uq_raw_articles_tenant_id_content_hash")
            .returning(RawArticle.id)
        )
        result = await self.db.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            return None
        await self.db.flush()
        loaded = await self.db.execute(select(RawArticle).where(RawArticle.id == inserted_id))
        return loaded.scalar_one()

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
