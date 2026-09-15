from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.source_ingestion.pagination import decode_article_cursor, encode_article_cursor
from backend.modules.source_ingestion.repository import SourceRepository
from backend.modules.source_ingestion.service import SourceIngestionService


def test_article_cursor_round_trip() -> None:
    created_at = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    article_id = uuid4()

    decoded = decode_article_cursor(
        encode_article_cursor(created_at=created_at, article_id=article_id)
    )

    assert decoded.created_at == created_at
    assert decoded.article_id == article_id


def test_article_cursor_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid article cursor"):
        decode_article_cursor("not-a-cursor")


def test_article_page_fetches_limit_plus_one_and_builds_next_cursor() -> None:
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    articles = [
        SimpleNamespace(id=uuid4(), created_at=now - timedelta(minutes=index))
        for index in range(3)
    ]
    calls: list[dict[str, object]] = []

    class FakeRepository:
        async def list_raw_articles(self, **kwargs: object) -> list[Any]:
            calls.append(kwargs)
            return articles

    async def _run() -> None:
        service = SourceIngestionService(cast(AsyncSession, object()))
        service.repo = cast(SourceRepository, FakeRepository())

        items, next_cursor, has_more = await service.list_raw_articles(uuid4(), limit=2)

        assert calls[0]["limit"] == 3
        assert items == articles[:2]
        assert has_more is True
        assert next_cursor is not None
        assert decode_article_cursor(next_cursor).article_id == articles[1].id

    asyncio.run(_run())


def test_repository_applies_limit_and_keyset_predicate_to_sql() -> None:
    statements: list[Any] = []

    class EmptyScalars:
        def all(self) -> list[object]:
            return []

    class EmptyResult:
        def scalars(self) -> EmptyScalars:
            return EmptyScalars()

    class FakeSession:
        async def execute(self, statement: Any) -> EmptyResult:
            statements.append(statement)
            return EmptyResult()

    cursor_time = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    repository = SourceRepository(cast(AsyncSession, FakeSession()))

    async def _run() -> None:
        await repository.list_raw_articles(
            tenant_id=uuid4(),
            limit=51,
            cursor_created_at=cursor_time,
            cursor_id=UUID("00000000-0000-0000-0000-000000000001"),
        )

    asyncio.run(_run())

    statement = statements[0]
    assert statement._limit_clause.value == 51
    sql = str(statement)
    assert "raw_articles.created_at <" in sql
    assert "raw_articles.id <" in sql
    assert "raw_articles.created_at DESC, raw_articles.id DESC" in sql
