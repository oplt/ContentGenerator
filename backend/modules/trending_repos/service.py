"""Trending repos service facade — GitHub fetch, ideas, Twitter, Telegram."""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.inference.providers import get_llm_provider
from backend.modules.trending_repos.github_client import (
    PERIOD_DAYS,
    REPO_ID_PATTERN,
    STAR_GAIN_PATTERN,
    GitHubTrendingClient,
    _extract_repo_id,
    _extract_repo_name,
    _extract_stars_gained,
    _parse_count,
    _parse_trending_repo,
    _stable_repo_id,
)
from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.product_ideas import (
    PLACEHOLDER_IDEA_VALUES,
    ProductIdeasGenerator,
    _FALLBACK_PRODUCT_HUNTER_PROMPT,
    _build_ideas_prompt,
    _format_product_hunter_result_preview,
    _is_placeholder_idea,
    _normalize_generated_ideas,
    _normalize_repo_assessment,
)
from backend.modules.trending_repos.repository import TrendingReposRepository
from backend.modules.trending_repos.schemas import TrendingReposListResponse
from backend.modules.trending_repos.telegram_digest import (
    TelegramDigestMixin,
    _escape_md,
    _serialize_trending_repo_response,
    serialize_trending_repo_response,
)
from backend.modules.trending_repos.twitter_callbacks import (
    handle_twitter_edit_message,
    handle_twitter_post_callback,
)
from backend.modules.trending_repos.twitter_publishing import TwitterPublishingMixin

logger = logging.getLogger(__name__)

# Compatibility re-exports historically defined in this module.
GITHUB_TRENDING_URL = "https://github.com/trending"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
MAX_README_PROMPT_CHARS = 6_000
MAX_REPOS = 25


class TrendingReposService(TwitterPublishingMixin, TelegramDigestMixin):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TrendingReposRepository(db)
        self.llm = get_llm_provider()
        self.github = GitHubTrendingClient()
        self.product_ideas = ProductIdeasGenerator(
            db,
            repo=self.repo,
            llm=self.llm,
            github_headers_builder=self.github._build_github_headers,
        )

    async def fetch_from_github(self, period: str) -> list[dict[str, Any]]:
        return await self.github.fetch_from_github(period)

    def _build_github_headers(self, accept: str) -> dict[str, str]:
        return self.github._build_github_headers(accept)

    async def _fetch_from_github_trending(self, period: str) -> list[dict[str, Any]]:
        return await self.github._fetch_from_github_trending(period)

    async def _fetch_from_github_search(self, period: str) -> list[dict[str, Any]]:
        return await self.github._fetch_from_github_search(period)

    def _parse_trending_html(self, html: str) -> list[dict[str, Any]]:
        return self.github._parse_trending_html(html)

    async def _enrich_trending_repos(
        self, repos: list[dict[str, Any]], client: httpx.AsyncClient | None = None
    ) -> list[dict[str, Any]]:
        _ = client
        return await self.github._enrich_trending_repos(repos)

    async def refresh_snapshot(self, tenant_id: uuid.UUID, period: str) -> list[TrendingRepo]:
        today = date.today()
        raw = await self.fetch_from_github(period)
        records = await self.repo.upsert_snapshot(tenant_id, period, today, raw)
        await self.db.flush()
        return records

    async def get_trending(self, tenant_id: uuid.UUID, period: str) -> TrendingReposListResponse:
        records = await self.repo.get_latest_by_period(tenant_id, period)
        snapshot_date = records[0].snapshot_date if records else date.today()
        return TrendingReposListResponse(
            repos=[serialize_trending_repo_response(r) for r in records],
            period=period,
            snapshot_date=snapshot_date,
            total=len(records),
        )

    def _load_product_hunter_prompt(self) -> str:
        return self.product_ideas._load_product_hunter_prompt()

    def _get_product_ideas_llm(self) -> Any:
        return self.product_ideas._get_product_ideas_llm()

    async def _ensure_product_ideas_llm_ready(self) -> None:
        await self.product_ideas._ensure_product_ideas_llm_ready()

    async def _get_llm_provider_health(self, provider_name: str) -> Any:
        return await self.product_ideas._get_llm_provider_health(provider_name)

    async def _fetch_repo_readme_excerpt(self, full_name: str) -> str | None:
        return await self.product_ideas._fetch_repo_readme_excerpt(full_name)

    async def generate_product_ideas(
        self, tenant_id: uuid.UUID, repo_id: uuid.UUID
    ) -> TrendingRepo:
        return await self.product_ideas.generate_product_ideas(tenant_id, repo_id)

    async def generate_ideas_for_daily_snapshot(self, tenant_id: uuid.UUID) -> list[TrendingRepo]:
        return await self.product_ideas.generate_ideas_for_daily_snapshot(tenant_id)


__all__ = [
    "GITHUB_REPO_URL",
    "GITHUB_SEARCH_URL",
    "GITHUB_TRENDING_URL",
    "MAX_README_PROMPT_CHARS",
    "MAX_REPOS",
    "PERIOD_DAYS",
    "PLACEHOLDER_IDEA_VALUES",
    "REPO_ID_PATTERN",
    "STAR_GAIN_PATTERN",
    "TrendingReposService",
    "_FALLBACK_PRODUCT_HUNTER_PROMPT",
    "_build_ideas_prompt",
    "_escape_md",
    "_extract_repo_id",
    "_extract_repo_name",
    "_extract_stars_gained",
    "_format_product_hunter_result_preview",
    "_is_placeholder_idea",
    "_normalize_generated_ideas",
    "_normalize_repo_assessment",
    "_parse_count",
    "_parse_trending_repo",
    "_serialize_trending_repo_response",
    "_stable_repo_id",
    "handle_twitter_edit_message",
    "handle_twitter_post_callback",
    "serialize_trending_repo_response",
]

