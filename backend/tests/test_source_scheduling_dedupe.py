"""Tests for SQL-backed source scheduling and batch article dedupe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from backend.modules.source_ingestion.repository import ArticleDedupeKeys, SourceRepository
from backend.modules.source_ingestion.scheduling import compute_next_poll_at, schedule_after_poll


def test_compute_next_poll_at_due_immediately_when_never_polled() -> None:
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert compute_next_poll_at(last_polled_at=None, polling_interval_minutes=30, now=now) == now


def test_compute_next_poll_at_from_last_poll() -> None:
    last = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    expected = last + timedelta(minutes=45)
    assert (
        compute_next_poll_at(last_polled_at=last, polling_interval_minutes=45, now=last)
        == expected
    )


def test_schedule_after_poll_uses_interval() -> None:
    polled = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert schedule_after_poll(polled_at=polled, polling_interval_minutes=15) == polled + timedelta(
        minutes=15
    )


def test_schedule_after_poll_clamps_zero_interval() -> None:
    polled = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert schedule_after_poll(polled_at=polled, polling_interval_minutes=0) == polled + timedelta(
        minutes=1
    )


def test_article_matches_keys_by_any_clause() -> None:
    article = SimpleNamespace(
        content_hash="hash-a",
        canonical_url="https://example.test/a",
        dedupe_key="dedupe-a",
        title_normalized="hello world",
    )
    assert SourceRepository._article_matches_keys(
        article,  # type: ignore[arg-type]
        ArticleDedupeKeys(
            canonical_url="https://other",
            content_hash="hash-a",
            dedupe_key=None,
            title_normalized=None,
        ),
    )
    assert SourceRepository._article_matches_keys(
        article,  # type: ignore[arg-type]
        ArticleDedupeKeys(
            canonical_url="https://example.test/a",
            content_hash="different",
            dedupe_key=None,
            title_normalized=None,
        ),
    )
    assert SourceRepository._article_matches_keys(
        article,  # type: ignore[arg-type]
        ArticleDedupeKeys(
            canonical_url="https://other",
            content_hash="different",
            dedupe_key="dedupe-a",
            title_normalized=None,
        ),
    )
    assert SourceRepository._article_matches_keys(
        article,  # type: ignore[arg-type]
        ArticleDedupeKeys(
            canonical_url="https://other",
            content_hash="different",
            dedupe_key=None,
            title_normalized="hello world",
        ),
    )
    assert not SourceRepository._article_matches_keys(
        article,  # type: ignore[arg-type]
        ArticleDedupeKeys(
            canonical_url="https://other",
            content_hash="different",
            dedupe_key="x",
            title_normalized="nope",
        ),
    )


def test_batch_match_assigns_first_hit_per_candidate() -> None:
    # Pure mapping logic: emulate find_existing_articles_batch body.
    candidates = [
        ArticleDedupeKeys("https://a", "h1", "d1", "t1"),
        ArticleDedupeKeys("https://b", "h2", "d2", "t2"),
        ArticleDedupeKeys("https://c", "h3", None, "t3"),
    ]
    rows = [
        SimpleNamespace(
            content_hash="h2",
            canonical_url="https://b",
            dedupe_key="d2",
            title_normalized="t2",
            id=uuid4(),
        ),
        SimpleNamespace(
            content_hash="other",
            canonical_url="https://c",
            dedupe_key=None,
            title_normalized="t3",
            id=uuid4(),
        ),
    ]
    matches: dict[int, object] = {}
    for index, keys in enumerate(candidates):
        for article in rows:
            if SourceRepository._article_matches_keys(article, keys):  # type: ignore[arg-type]
                matches[index] = article
                break
    assert 0 not in matches
    assert 1 in matches
    assert 2 in matches
    assert matches[1].content_hash == "h2"  # type: ignore[attr-defined]
