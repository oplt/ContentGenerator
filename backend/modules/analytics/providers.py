"""
Platform metrics sync providers for analytics.

Each provider fetches engagement metrics for a published post
and returns a normalised dict ready to populate AnalyticsSnapshot.

Providers:
  - XMetricsProvider     — X API v2 /tweets/{id}?tweet.fields=public_metrics
  - InstagramMetricsProvider — Graph API /{post_id}/insights
  - YouTubeMetricsProvider   — YouTube Data API /videos?part=statistics

All providers accept the raw access_token (decrypted before call)
and return a MetricsResult or raise on unrecoverable errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from backend.core.config import settings


@dataclass
class MetricsResult:
    impressions: int = 0
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_seconds: int = 0
    saves: int = 0
    avg_watch_duration: float | None = None
    retention: dict = field(default_factory=dict)
    profile_visits: int = 0
    follows: int = 0
    ctr: float | None = None
    sync_source: str = "synthetic"
    raw_payload: dict = field(default_factory=dict)


class XMetricsProvider:
    """Fetches tweet public_metrics from X API v2."""

    BASE_URL = settings.X_API_BASE_URL.rstrip("/")

    def __init__(self, access_token: str):
        self.access_token = access_token

    async def fetch(self, tweet_id: str) -> MetricsResult:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self.BASE_URL}/2/tweets/{tweet_id}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={"tweet.fields": "public_metrics"},
            )
            response.raise_for_status()
            data = response.json()

        metrics = data.get("data", {}).get("public_metrics", {})
        impressions = metrics.get("impression_count", 0)
        return MetricsResult(
            impressions=impressions,
            views=impressions,
            likes=metrics.get("like_count", 0),
            comments=metrics.get("reply_count", 0),
            shares=metrics.get("retweet_count", 0) + metrics.get("quote_count", 0),
            ctr=None,
            sync_source="x_api",
            raw_payload=metrics,
        )


class InstagramMetricsProvider:
    """Fetches post insights from Instagram Graph API."""

    BASE_URL = settings.INSTAGRAM_GRAPH_BASE_URL.rstrip("/")

    def __init__(self, access_token: str):
        self.access_token = access_token

    async def fetch(self, post_id: str) -> MetricsResult:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self.BASE_URL}/v20.0/{post_id}/insights",
                params={
                    "metric": "impressions,reach,likes_count,comments_count,shares",
                    "access_token": self.access_token,
                },
            )
            response.raise_for_status()
            data = response.json()

        raw: dict[str, int] = {}
        for item in data.get("data", []):
            raw[item["name"]] = item.get("values", [{}])[0].get("value", 0)

        impressions = raw.get("impressions", 0)
        reach = raw.get("reach", 0)
        ctr = round(reach / impressions, 4) if impressions else None
        return MetricsResult(
            impressions=impressions,
            views=reach,
            likes=raw.get("likes_count", 0),
            comments=raw.get("comments_count", 0),
            shares=raw.get("shares", 0),
            ctr=ctr,
            sync_source="instagram_api",
            raw_payload=raw,
        )


class YouTubeMetricsProvider:
    """Fetches video statistics from YouTube Data API v3."""

    BASE_URL = settings.YOUTUBE_API_BASE_URL.rstrip("/")

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def fetch(self, video_id: str) -> MetricsResult:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self.BASE_URL}/youtube/v3/videos",
                params={
                    "part": "statistics",
                    "id": video_id,
                    "key": self.api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        stats = data.get("items", [{}])[0].get("statistics", {})
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        return MetricsResult(
            impressions=views,
            views=views,
            likes=likes,
            comments=comments,
            shares=0,
            avg_watch_duration=None,
            ctr=None,
            sync_source="youtube_api",
            raw_payload=stats,
        )


def get_metrics_provider(
    platform: str,
    *,
    access_token: str = "",
    api_key: str = "",
) -> XMetricsProvider | InstagramMetricsProvider | YouTubeMetricsProvider | None:
    """
    Factory: returns a provider if credentials are available, else None.
    Callers should fall back to synthetic data when None is returned.
    """
    if platform == "x" and access_token:
        return XMetricsProvider(access_token)
    if platform == "instagram" and access_token:
        return InstagramMetricsProvider(access_token)
    if platform == "youtube" and (access_token or api_key):
        return YouTubeMetricsProvider(api_key or access_token)
    return None
