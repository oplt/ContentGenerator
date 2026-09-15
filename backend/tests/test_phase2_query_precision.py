"""Unit tests for Phase 2 dedupe maps, bulk insert shape, and stale-claim batching."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.job_claiming import JobClaimingMixin
from backend.modules.publishing.models import PublishingAttemptStatus, PublishingJobStatus
from backend.modules.source_ingestion.repository import ArticleDedupeKeys, SourceRepository


def test_match_candidates_is_linear_with_hash_precedence() -> None:
    hash_row = SimpleNamespace(
        content_hash="h1",
        canonical_url="https://a",
        dedupe_key="d1",
        title_normalized="t1",
        id=uuid4(),
    )
    title_row = SimpleNamespace(
        content_hash="other",
        canonical_url="https://other",
        dedupe_key=None,
        title_normalized="t2",
        id=uuid4(),
    )
    # Same title as later candidate; hash must win when both collide.
    dual = SimpleNamespace(
        content_hash="h3",
        canonical_url="https://c",
        dedupe_key="d3",
        title_normalized="shared-title",
        id=uuid4(),
    )
    title_only = SimpleNamespace(
        content_hash="hx",
        canonical_url="https://x",
        dedupe_key=None,
        title_normalized="shared-title",
        id=uuid4(),
    )
    candidates = [
        ArticleDedupeKeys("https://miss", "h1", None, None),
        ArticleDedupeKeys("https://miss", "nope", None, "t2"),
        ArticleDedupeKeys("https://miss", "h3", None, "shared-title"),
        ArticleDedupeKeys("https://none", "none", None, "absent"),
    ]
    matches = SourceRepository._match_candidates_to_rows(
        candidates,
        cast(Any, [title_only, dual, title_row, hash_row]),
    )
    assert matches[0] is hash_row
    assert matches[1] is title_row
    assert matches[2] is dual  # hash map wins over earlier title_only row
    assert 3 not in matches


def test_insert_raw_articles_conflict_safe_uses_single_returning_statement() -> None:
    execute = AsyncMock()
    flush = AsyncMock()

    class FakeResult:
        def scalars(self) -> Any:
            return SimpleNamespace(all=lambda: [SimpleNamespace(id=uuid4())])

    execute.return_value = FakeResult()
    session = SimpleNamespace(execute=execute, flush=flush)
    repo = SourceRepository(cast(AsyncSession, session))

    article = SimpleNamespace(
        id=None,
        tenant_id=uuid4(),
        source_id=uuid4(),
        fetch_run_id=None,
        url="https://example.test/1",
        canonical_url="https://example.test/1",
        dedupe_key="k1",
        title_normalized="title",
        content_hash="hash-1",
        title="Title",
        summary=None,
        body=None,
        author=None,
        language=None,
        published_at=None,
        extraction_confidence=0.5,
        source_metadata={},
        deleted_at=None,
    )

    async def _run() -> None:
        inserted = await repo.insert_raw_articles_conflict_safe(cast(Any, [article, article]))
        assert len(inserted) == 1
        assert execute.await_count == 1
        assert flush.await_count == 1
        statement = execute.await_args.args[0]
        assert hasattr(statement, "on_conflict_do_nothing") or "on_conflict" in type(statement).__name__.lower()
        compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
        assert "raw_articles" in compiled.lower()

    asyncio.run(_run())


def test_stale_claim_recovery_loads_latest_attempts_in_one_query() -> None:
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    job_a = SimpleNamespace(
        id=uuid4(),
        status=PublishingJobStatus.CLAIMED.value,
        claim_expires_at=now,
        claimed_at=now,
        worker_id="w1",
        provider_payload={},
        failure_reason=None,
        scheduled_for=None,
    )
    job_b = SimpleNamespace(
        id=uuid4(),
        status=PublishingJobStatus.RUNNING.value,
        claim_expires_at=now,
        claimed_at=now,
        worker_id="w1",
        provider_payload={},
        failure_reason=None,
        scheduled_for=None,
    )
    attempt_a = SimpleNamespace(
        publishing_job_id=job_a.id,
        status=PublishingAttemptStatus.SUCCEEDED.value,
        error_message=None,
    )
    attempt_b = SimpleNamespace(
        publishing_job_id=job_b.id,
        status=PublishingAttemptStatus.PREPARED.value,
        error_message=None,
    )

    class FakeScalars:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def all(self) -> list[object]:
            return self._rows

    class FakeResult:
        def __init__(self, rows: list[object]) -> None:
            self._rows = rows

        def scalars(self) -> FakeScalars:
            return FakeScalars(self._rows)

    calls: list[str] = []

    class FakeSession:
        async def execute(self, statement: object) -> FakeResult:
            sql = str(statement.compile(dialect=postgresql.dialect())).lower()
            if "publishing_jobs" in sql:
                calls.append("stale_jobs")
                return FakeResult([job_a, job_b])
            if "publishing_attempts" in sql:
                calls.append("attempts")
                assert "distinct on" in sql
                return FakeResult([attempt_a, attempt_b])
            raise AssertionError(f"unexpected SQL: {sql}")

        async def flush(self) -> None:
            calls.append("flush")

    class Repo(JobClaimingMixin):
        def __init__(self) -> None:
            self.db = cast(AsyncSession, FakeSession())

    async def _run() -> None:
        recovered = await Repo()._recover_stale_claims(now=now, batch_size=10)
        assert recovered == 2
        assert job_a.status == PublishingJobStatus.MANUAL_REQUIRED.value
        assert job_b.status == PublishingJobStatus.SCHEDULED.value
        assert calls == ["stale_jobs", "attempts", "flush"]

    asyncio.run(_run())
