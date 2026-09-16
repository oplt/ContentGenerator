"""Raw article persistence and deduplication operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.source_ingestion.models import RawArticle


@dataclass(frozen=True, slots=True)
class ArticleDedupeKeys:
    canonical_url: str
    content_hash: str
    dedupe_key: str | None = None
    title_normalized: str | None = None


class ArticleRepositoryMixin:
    db: AsyncSession

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
        return bool(
            article.content_hash == keys.content_hash
            or article.canonical_url == keys.canonical_url
            or (keys.dedupe_key and article.dedupe_key == keys.dedupe_key)
            or (keys.title_normalized and article.title_normalized == keys.title_normalized)
        )

    @staticmethod
    def _match_candidates_to_rows(
        candidates: list[ArticleDedupeKeys],
        existing_rows: list[RawArticle],
    ) -> dict[int, RawArticle]:
        """Match candidates in hash, URL, dedupe-key, then title precedence."""
        by_hash: dict[str, RawArticle] = {}
        by_url: dict[str, RawArticle] = {}
        by_dedupe: dict[str, RawArticle] = {}
        by_title: dict[str, RawArticle] = {}
        for article in existing_rows:
            by_hash.setdefault(article.content_hash, article)
            by_url.setdefault(article.canonical_url, article)
            if article.dedupe_key:
                by_dedupe.setdefault(article.dedupe_key, article)
            if article.title_normalized:
                by_title.setdefault(article.title_normalized, article)

        matches: dict[int, RawArticle] = {}
        for index, keys in enumerate(candidates):
            match = by_hash.get(keys.content_hash) or by_url.get(keys.canonical_url)
            if match is None and keys.dedupe_key:
                match = by_dedupe.get(keys.dedupe_key)
            if match is None and keys.title_normalized:
                match = by_title.get(keys.title_normalized)
            if match is not None:
                matches[index] = match
        return matches

    async def find_existing_articles_batch(
        self,
        *,
        tenant_id: UUID,
        candidates: list[ArticleDedupeKeys],
    ) -> dict[int, RawArticle]:
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
        return self._match_candidates_to_rows(candidates, list(result.scalars().all()))

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

    def _raw_article_values(self, article: RawArticle) -> dict[str, object]:
        article_id = article.id or uuid4()
        article.id = article_id
        return {
            "id": article_id,
            "tenant_id": article.tenant_id,
            "source_id": article.source_id,
            "fetch_run_id": article.fetch_run_id,
            "url": article.url,
            "canonical_url": article.canonical_url,
            "dedupe_key": article.dedupe_key,
            "title_normalized": article.title_normalized,
            "content_hash": article.content_hash,
            "title": article.title,
            "summary": article.summary,
            "body": article.body,
            "author": article.author,
            "language": article.language,
            "published_at": article.published_at,
            "extraction_confidence": article.extraction_confidence,
            "source_metadata": article.source_metadata or {},
            "deleted_at": article.deleted_at,
        }

    async def insert_raw_article_conflict_safe(self, article: RawArticle) -> RawArticle | None:
        inserted = await self.insert_raw_articles_conflict_safe([article])
        return inserted[0] if inserted else None

    async def insert_raw_articles_conflict_safe(self, articles: list[RawArticle]) -> list[RawArticle]:
        if not articles:
            return []
        stmt = (
            insert(RawArticle)
            .values([self._raw_article_values(article) for article in articles])
            .on_conflict_do_nothing(constraint="uq_raw_articles_tenant_id_content_hash")
            .returning(RawArticle)
        )
        result = await self.db.execute(stmt)
        inserted = list(result.scalars().all())
        await self.db.flush()
        return inserted

    async def list_raw_articles(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        cursor_created_at: datetime | None = None,
        cursor_id: UUID | None = None,
    ) -> list[RawArticle]:
        statement = select(RawArticle).where(
            RawArticle.tenant_id == tenant_id,
            RawArticle.deleted_at.is_(None),
        )
        if cursor_created_at is not None and cursor_id is not None:
            statement = statement.where(
                or_(
                    RawArticle.created_at < cursor_created_at,
                    and_(RawArticle.created_at == cursor_created_at, RawArticle.id < cursor_id),
                )
            )
        result = await self.db.execute(
            statement.order_by(RawArticle.created_at.desc(), RawArticle.id.desc()).limit(limit)
        )
        return list(result.scalars().all())
