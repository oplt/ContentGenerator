"""Unit tests for analytics sync batching and aggregate math."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncio

from backend.modules.analytics.models import AnalyticsSnapshot, TemplatePerformance
from backend.modules.analytics.repository import PostSyncContext
from backend.modules.analytics.service import AnalyticsService


def test_compute_engagement_score_clamped() -> None:
    tp = TemplatePerformance(
        tenant_id=uuid4(),
        platform="x",
        tone="authoritative",
        content_vertical="general",
        sample_count=1,
        avg_likes=10_000,
        avg_shares=5_000,
        avg_comments=2_000,
        avg_ctr=1.0,
    )
    assert AnalyticsService._compute_engagement_score(tp) == 1.0


def test_compute_engagement_score_zero_samples() -> None:
    tp = TemplatePerformance(
        tenant_id=uuid4(),
        platform="x",
        tone="authoritative",
        content_vertical="general",
        sample_count=0,
    )
    assert AnalyticsService._compute_engagement_score(tp) == 0.0


def test_running_average_formula() -> None:
    """Document ON CONFLICT math: (old * n + new) / (n + 1)."""
    n = 4
    old_avg = 100.0
    new_value = 200.0
    assert (old_avg * n + new_value) / (n + 1) == 120.0


def test_sync_snapshots_uses_bounded_repo_calls() -> None:
    """N posts → fixed DB prep queries, not O(N) snapshot/job/context reads."""

    async def _run() -> None:
        tenant_id = uuid4()
        posts = []
        contexts = []
        for _ in range(5):
            post = SimpleNamespace(
                id=uuid4(),
                tenant_id=tenant_id,
                publishing_job_id=uuid4(),
                social_account_id=None,
                platform="x",
                post_type="text",
                raw_payload={},
                external_post_id=None,
            )
            posts.append(post)
            contexts.append(
                PostSyncContext(
                    post=post,  # type: ignore[arg-type]
                    publish_job_id=post.publishing_job_id,
                    tone="authoritative",
                    content_vertical="general",
                )
            )

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        service = AnalyticsService(db)
        service.repo.list_post_sync_contexts = AsyncMock(return_value=contexts)
        service.repo.get_snapshots_for_posts = AsyncMock(return_value={})
        service.publishing_repo.get_tokens_for_accounts = AsyncMock(return_value={})
        service.repo.upsert_snapshot = AsyncMock(
            side_effect=lambda **kwargs: (
                AnalyticsSnapshot(
                    tenant_id=tenant_id,
                    published_post_id=kwargs["published_post_id"],
                    platform=kwargs["platform"],
                    snapshot_date=kwargs["snapshot_date"],
                    content_format=kwargs["content_format"],
                    impressions=kwargs["impressions"],
                    views=kwargs["views"],
                    likes=kwargs["likes"],
                    comments=kwargs["comments"],
                    shares=kwargs["shares"],
                    watch_time_seconds=kwargs["watch_time_seconds"],
                    ctr=kwargs["ctr"],
                    sync_source=kwargs["sync_source"],
                    raw_payload=kwargs["raw_payload"],
                ),
                True,
            )
        )
        service.repo.apply_template_performance_sample = AsyncMock(
            return_value=TemplatePerformance(
                tenant_id=tenant_id,
                platform="x",
                tone="authoritative",
                content_vertical="general",
                sample_count=1,
                avg_impressions=1200.0,
                avg_likes=200.0,
                avg_comments=20.0,
                avg_shares=16.0,
                avg_ctr=0.08,
            )
        )
        # Guard: legacy N+1 paths must not be used
        service.repo.get_snapshot_for_post = AsyncMock(side_effect=AssertionError("N+1 snapshot"))
        service.publishing_repo.get_publishing_job = AsyncMock(side_effect=AssertionError("N+1 job"))
        service.publishing_repo.list_published_posts = AsyncMock(
            side_effect=AssertionError("use list_post_sync_contexts")
        )
        service._resolve_post_context = AsyncMock(side_effect=AssertionError("N+1 context"))

        snapshots = await service.sync_snapshots(tenant_id)
        assert len(snapshots) == 5
        service.repo.list_post_sync_contexts.assert_awaited_once_with(tenant_id)
        service.repo.get_snapshots_for_posts.assert_awaited_once()
        assert service.repo.get_snapshots_for_posts.await_args.args[1] == date.today()
        service.publishing_repo.get_tokens_for_accounts.assert_awaited_once()
        assert service.repo.upsert_snapshot.await_count == 5
        assert service.repo.apply_template_performance_sample.await_count == 5

    asyncio.run(_run())


def test_sync_skips_template_update_for_existing_daily_snapshot() -> None:
    async def _run() -> None:
        tenant_id = uuid4()
        post_id = uuid4()
        post = SimpleNamespace(
            id=post_id,
            tenant_id=tenant_id,
            publishing_job_id=uuid4(),
            social_account_id=None,
            platform="x",
            post_type="text",
            raw_payload={},
            external_post_id=None,
        )
        ctx = PostSyncContext(
            post=post,  # type: ignore[arg-type]
            publish_job_id=post.publishing_job_id,
            tone="authoritative",
            content_vertical="general",
        )
        existing = AnalyticsSnapshot(
            tenant_id=tenant_id,
            published_post_id=post_id,
            platform="x",
            snapshot_date=date.today(),
            content_format="text",
            impressions=1,
            views=1,
            likes=1,
            comments=0,
            shares=0,
            watch_time_seconds=0,
        )

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        service = AnalyticsService(db)
        service.repo.list_post_sync_contexts = AsyncMock(return_value=[ctx])
        service.repo.get_snapshots_for_posts = AsyncMock(return_value={post_id: existing})
        service.publishing_repo.get_tokens_for_accounts = AsyncMock(return_value={})
        service.repo.upsert_snapshot = AsyncMock(return_value=(existing, True))
        service.repo.apply_template_performance_sample = AsyncMock()

        await service.sync_snapshots(tenant_id)
        service.repo.apply_template_performance_sample.assert_not_awaited()

    asyncio.run(_run())
