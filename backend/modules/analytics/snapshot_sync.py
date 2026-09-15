from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.analytics.metrics import AnalyticsMetrics
from backend.modules.analytics.models import AnalyticsSnapshot, PostAnalytics
from backend.modules.analytics.repository import AnalyticsRepository
from backend.modules.publishing.account_ops import account_label_from_snapshot
from backend.modules.publishing.repository import PublishingRepository

logger = logging.getLogger(__name__)


async def sync_post_snapshots(
    *,
    db: AsyncSession,
    repo: AnalyticsRepository,
    publishing_repo: PublishingRepository,
    metrics: AnalyticsMetrics,
    tenant_id: UUID,
    update_template_performance,
    synthetic_metrics,
) -> list[AnalyticsSnapshot]:
    today = date.today()
    contexts = await repo.list_post_sync_contexts(tenant_id)
    if not contexts:
        return []

    post_ids = [ctx.post.id for ctx in contexts]
    existing_by_post = await repo.get_snapshots_for_posts(post_ids, today)

    account_ids = [
        ctx.post.social_account_id
        for ctx in contexts
        if getattr(ctx.post, "social_account_id", None) is not None
    ]
    tokens_by_account = await publishing_repo.get_tokens_for_accounts(
        list({account_id for account_id in account_ids if account_id is not None})
    )

    snapshots: list[AnalyticsSnapshot] = []
    from backend.core.config import settings as app_settings
    from backend.core.http import map_concurrent

    async def _metrics_for(ctx: Any) -> dict[str, object]:
        post = ctx.post
        return await metrics.fetch_real_metrics(
            post,
            token_row=tokens_by_account.get(post.social_account_id) if post.social_account_id else None,
        )

    metrics_outcomes = await map_concurrent(
        contexts,
        _metrics_for,
        limit=app_settings.HTTP_PROVIDER_ANALYTICS_CONCURRENCY,
        return_exceptions=True,
    )

    for ctx, metrics_outcome in zip(contexts, metrics_outcomes, strict=True):
        post = ctx.post
        if isinstance(metrics_outcome, BaseException):
            logger.warning(
                "metrics_fetch_failed platform=%s post_id=%s error=%s",
                post.platform,
                post.id,
                metrics_outcome,
            )
            metrics_payload = synthetic_metrics(post)
        else:
            metrics_payload = metrics_outcome
        impressions = int(cast(int, metrics_payload["impressions"]))
        views = int(cast(int, metrics_payload["views"]))
        likes = int(cast(int, metrics_payload["likes"]))
        comments = int(cast(int, metrics_payload["comments"]))
        shares = int(cast(int, metrics_payload["shares"]))
        watch_time_seconds = int(cast(int, metrics_payload["watch_time_seconds"]))
        ctr = float(cast(float, metrics_payload["ctr"]))
        sync_source = str(cast(str, metrics_payload["sync_source"]))
        raw_payload = cast(dict[str, str], metrics_payload.get("raw_payload") or {})
        saves = int(cast(int, metrics_payload.get("saves", 0)))
        avg_watch_duration = cast(float | None, metrics_payload.get("avg_watch_duration"))
        retention = cast(dict[str, str], metrics_payload.get("retention") or {})
        profile_visits = int(cast(int, metrics_payload.get("profile_visits", 0)))
        follows = int(cast(int, metrics_payload.get("follows", 0)))

        account_label = account_label_from_snapshot(
            getattr(post, "account_display_snapshot", None) or {},
            platform=str(post.platform),
        )
        snapshot, was_inserted = await repo.upsert_snapshot(
            tenant_id=tenant_id,
            published_post_id=post.id,
            platform=post.platform,
            snapshot_date=today,
            topic=post.raw_payload.get("topic") if post.raw_payload else None,
            content_format=post.post_type,
            impressions=impressions,
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            watch_time_seconds=watch_time_seconds,
            ctr=ctr,
            sync_source=sync_source,
            raw_payload=raw_payload,
            social_account_id=post.social_account_id,
            account_label=account_label,
        )
        if post.id in existing_by_post:
            was_inserted = False
        snapshots.append(snapshot)

        db.add(
            PostAnalytics(
                tenant_id=tenant_id,
                publish_job_id=ctx.publish_job_id,
                published_post_id=post.id,
                platform=post.platform,
                fetched_at=datetime.now(timezone.utc),
                impressions=impressions,
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                saves=saves,
                watch_time=watch_time_seconds,
                avg_watch_duration=avg_watch_duration,
                retention=retention,
                profile_visits=profile_visits,
                follows=follows,
                ctr=ctr,
                raw_metrics=raw_payload,
            )
        )

        if was_inserted:
            try:
                await update_template_performance(
                    tenant_id,
                    snapshot,
                    tone=ctx.tone,
                    content_vertical=ctx.content_vertical,
                )
            except Exception:
                pass

    await db.flush()
    return snapshots
