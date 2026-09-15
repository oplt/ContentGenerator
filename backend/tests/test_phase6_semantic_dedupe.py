"""Phase 6: tokenize-once semantic duplicate comparison."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from backend.modules.source_ingestion.adapters import FetchedArticle, tokenize_for_similarity
from backend.modules.source_ingestion.fetch_cache import (
    build_article_token_index,
    semantic_duplicate,
)


def _article(title: str, summary: str = "") -> FetchedArticle:
    return FetchedArticle(
        url="https://example.test/a",
        canonical_url="https://example.test/a",
        title=title,
        summary=summary,
        body=None,
        author=None,
        published_at=None,
        metadata={},
    )


def _raw(title: str, summary: str = "") -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), title=title, summary=summary)


def test_build_article_token_index_tokenizes_once_reusable() -> None:
    recent = [_raw("Alpha beta gamma news"), _raw("Completely different story")]
    index = build_article_token_index(recent)  # type: ignore[arg-type]
    assert len(index) == 2
    assert index[0][1] == frozenset(tokenize_for_similarity("Alpha beta gamma news"))


def test_semantic_duplicate_reuses_token_index() -> None:
    recent = [
        _raw("OpenAI releases new model for developers"),
        _raw("Unrelated sports match result"),
    ]
    index = build_article_token_index(recent)  # type: ignore[arg-type]
    candidate = _article("OpenAI releases new model for developers")
    match = semantic_duplicate(candidate, token_index=index)
    assert match is recent[0]

    miss = semantic_duplicate(_article("Local weather forecast sunny"), token_index=index)
    assert miss is None


def test_semantic_duplicate_builds_index_when_omitted() -> None:
    recent = [_raw("Shared headline about chips and fabs")]
    candidate = _article("Shared headline about chips and fabs")
    assert semantic_duplicate(candidate, recent) is recent[0]  # type: ignore[arg-type]
