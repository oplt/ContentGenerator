from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.analytics.schemas import AnalyticsOverviewResponse, ChartPoint, LearningLogEntry


def aggregate_snapshot_charts(snapshots: list[Any]) -> dict[str, Any]:
    """Bucket snapshot metrics into overview chart series."""
    posts_by_date: dict[str, float] = defaultdict(float)
    by_platform: dict[str, float] = defaultdict(float)
    by_account: dict[str, float] = defaultdict(float)
    by_format: dict[str, float] = defaultdict(float)
    by_topic: dict[str, float] = defaultdict(float)
    hook_performance_raw: dict[str, float] = defaultdict(float)
    post_time_raw: dict[str, float] = defaultdict(float)
    brand_performance_raw: dict[str, float] = defaultdict(float)
    topic_follow_raw: dict[str, float] = defaultdict(float)
    platform_comparison_raw: dict[str, tuple[float, float]] = defaultdict(lambda: (0.0, 0.0))
    for snapshot in snapshots:
        posts_by_date[str(snapshot.snapshot_date)] += snapshot.views
        by_platform[snapshot.platform] += snapshot.views
        account_key = snapshot.account_label or (
            f"{snapshot.platform} · {str(snapshot.social_account_id)[:8]}"
            if snapshot.social_account_id
            else snapshot.platform
        )
        by_account[account_key] += snapshot.views
        by_format[snapshot.content_format] += snapshot.views
        raw_payload = snapshot.raw_payload or {}
        hook_label = str(raw_payload.get("hook") or raw_payload.get("hook_label") or "default")
        hook_performance_raw[hook_label] += snapshot.views
        post_hour = str(raw_payload.get("publish_hour") or "unknown")
        post_time_raw[post_hour] += snapshot.views
        brand_label = str(raw_payload.get("brand") or raw_payload.get("brand_profile") or "default")
        brand_performance_raw[brand_label] += snapshot.views
        current_views, current_engagement = platform_comparison_raw[snapshot.platform]
        platform_comparison_raw[snapshot.platform] = (
            current_views + snapshot.views,
            current_engagement + snapshot.likes + snapshot.comments + snapshot.shares,
        )
        if snapshot.topic:
            by_topic[snapshot.topic] += snapshot.views
            topic_follow_raw[snapshot.topic] += float(raw_payload.get("follows", 0))
    return {
        "posts_by_date": posts_by_date,
        "by_platform": by_platform,
        "by_account": by_account,
        "by_format": by_format,
        "by_topic": by_topic,
        "hook_performance_raw": hook_performance_raw,
        "post_time_raw": post_time_raw,
        "brand_performance_raw": brand_performance_raw,
        "topic_follow_raw": topic_follow_raw,
        "platform_comparison_raw": platform_comparison_raw,
    }


async def build_learning_log(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    platform_views: dict[str, float],
    topic_views: dict[str, float],
    post_time: dict[str, float],
) -> list[LearningLogEntry]:
    learning_log: list[LearningLogEntry] = []
    total_platform_views = sum(platform_views.values()) or 1.0
    for platform, views in sorted(platform_views.items(), key=lambda item: item[1], reverse=True)[:3]:
        learning_log.append(
            LearningLogEntry(
                category="scoring_weight",
                message=f"Platform weight shifted toward {platform}",
                weight=round(views / total_platform_views, 4),
                recommendation=f"Prefer prompts tailored for {platform}",
            )
        )
    for topic, _views in sorted(topic_views.items(), key=lambda item: item[1], reverse=True)[:2]:
        learning_log.append(
            LearningLogEntry(
                category="prompt_recommendation",
                message=f"Topic '{topic}' is outperforming current baseline",
                recommendation=f"Increase hook density and CTA specificity for {topic}",
            )
        )
    for hour, _views in sorted(post_time.items(), key=lambda item: item[1], reverse=True)[:1]:
        learning_log.append(
            LearningLogEntry(
                category="publish_timing",
                message=f"Best publish hour currently {hour}",
                recommendation="Bias schedules toward the strongest hour bucket",
            )
        )
    try:
        from backend.modules.analytics.optimization import OptimizationService

        recommendations = await OptimizationService(db).recommend(tenant_id, top_n=2)
        for rec in recommendations:
            learning_log.append(
                LearningLogEntry(
                    category="prompt_recommendation",
                    message=f"Top template for {rec.platform}: tone={rec.tone}, vertical={rec.content_vertical}",
                    weight=rec.engagement_score,
                    recommendation=", ".join(rec.reasons),
                )
            )
    except Exception:
        pass
    return learning_log
