"""GitHub trending fetch client — HTML scrape with Search API fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup

from backend.core.config import settings
from backend.core.http import map_concurrent, request
from backend.modules.trending_repos.github_parse import (
    REPO_ID_PATTERN,
    STAR_GAIN_PATTERN,
    _extract_repo_id,
    _extract_repo_name,
    _extract_stars_gained,
    _parse_count,
    _parse_trending_repo,
    _stable_repo_id,
    parse_trending_repo,
)

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
MAX_REPOS = 25

PERIOD_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}


class GitHubTrendingClient:
    """Fetch and parse GitHub trending repositories."""

    async def fetch_from_github(self, period: str) -> list[dict[str, Any]]:
        try:
            repos = await self._fetch_from_github_trending(period)
        except Exception:
            logger.exception(
                "Failed to fetch GitHub Trending HTML for period=%s; falling back to Search API",
                period,
            )
        else:
            if repos:
                logger.info("Fetched %d trending repos for period=%s", len(repos), period)
                return repos
            logger.warning(
                "GitHub Trending HTML returned no repos for period=%s; falling back to Search API",
                period,
            )

        repos = await self._fetch_from_github_search(period)
        logger.info("Fetched %d fallback trending repos for period=%s", len(repos), period)
        return repos

    def _build_github_headers(self, accept: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": accept,
            "User-Agent": "content-generator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        github_token = getattr(settings, "GITHUB_TOKEN", None)
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        return headers

    async def _fetch_from_github_trending(self, period: str) -> list[dict[str, Any]]:
        import asyncio

        resp = await request(
            "GET",
            GITHUB_TRENDING_URL,
            provider="github",
            headers=self._build_github_headers("text/html,application/xhtml+xml"),
            params={"since": period},
            timeout=15.0,
        )
        resp.raise_for_status()
        repos = await asyncio.to_thread(self._parse_trending_html, resp.text)

        if getattr(settings, "GITHUB_TOKEN", None):
            repos = await self._enrich_trending_repos(repos)

        return repos

    async def _fetch_from_github_search(self, period: str) -> list[dict[str, Any]]:
        """
        Fetch fallback trending repos from GitHub Search API.

        Trending = repos created in the last N days, sorted by stars descending.
        This is a reliable proxy: high-star repos in a short creation window
        are genuinely going viral.
        """
        days = PERIOD_DAYS.get(period, 1)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"created:>{since}"

        params: dict[str, str | int] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": MAX_REPOS,
        }

        resp = await request(
            "GET",
            GITHUB_SEARCH_URL,
            provider="github",
            headers=self._build_github_headers("application/vnd.github+json"),
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        repos = []
        for item in data.get("items", []):
            repos.append(
                {
                    "github_id": item["id"],
                    "name": item["full_name"],
                    "full_name": item["full_name"],
                    "description": item.get("description") or None,
                    "html_url": item["html_url"],
                    "language": item.get("language") or None,
                    "topics": item.get("topics") or [],
                    "stars_count": item.get("stargazers_count", 0),
                    "forks_count": item.get("forks_count", 0),
                    "watchers_count": item.get("watchers_count", 0),
                    "open_issues_count": item.get("open_issues_count", 0),
                    # Stars gained ≈ total stars (repo is young — created within window)
                    "stars_gained": item.get("stargazers_count", 0),
                }
            )
        return repos

    def _parse_trending_html(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        repos: list[dict[str, Any]] = []
        seen: set[str] = set()

        for article in soup.select("article.Box-row"):
            repo = parse_trending_repo(article)
            if repo is None or repo["full_name"] in seen:
                continue
            repos.append(repo)
            seen.add(repo["full_name"])
            if len(repos) >= MAX_REPOS:
                break

        return repos

    async def _enrich_trending_repos(
        self, repos: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Enrich repos via GitHub API with bounded concurrency; keep partial successes."""
        from backend.core.config import settings as app_settings

        async def _enrich_one(repo: dict[str, Any]) -> dict[str, Any]:
            try:
                resp = await request(
                    "GET",
                    f"{GITHUB_REPO_URL}/{repo['full_name']}",
                    provider="github",
                    headers=self._build_github_headers("application/vnd.github+json"),
                    timeout=15.0,
                )
                resp.raise_for_status()
                details = resp.json()
            except Exception:
                logger.warning(
                    "Failed to enrich trending repo %s from GitHub API", repo["full_name"]
                )
                return repo

            return {
                **repo,
                "github_id": int(details.get("id") or repo["github_id"]),
                "description": details.get("description") or repo["description"],
                "language": details.get("language") or repo["language"],
                "topics": details.get("topics") or repo["topics"],
                "stars_count": int(details.get("stargazers_count") or repo["stars_count"]),
                "forks_count": int(details.get("forks_count") or repo["forks_count"]),
                "watchers_count": int(details.get("watchers_count") or repo["watchers_count"]),
                "open_issues_count": int(
                    details.get("open_issues_count") or repo["open_issues_count"]
                ),
            }

        outcomes = await map_concurrent(
            repos,
            _enrich_one,
            limit=app_settings.HTTP_PROVIDER_GITHUB_CONCURRENCY,
            return_exceptions=True,
        )
        enriched: list[dict[str, Any]] = []
        for index, outcome in enumerate(outcomes):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "Failed to enrich trending repo %s from GitHub API",
                    repos[index]["full_name"],
                )
                enriched.append(repos[index])
            else:
                enriched.append(outcome)
        return enriched


# Re-export Telegram callbacks historically housed in this module.
from backend.modules.trending_repos.twitter_callbacks import (  # noqa: E402
    handle_twitter_edit_message,
    handle_twitter_post_callback,
)

__all__ = [
    "GITHUB_REPO_URL",
    "GITHUB_SEARCH_URL",
    "GITHUB_TRENDING_URL",
    "GitHubTrendingClient",
    "MAX_REPOS",
    "PERIOD_DAYS",
    "REPO_ID_PATTERN",
    "STAR_GAIN_PATTERN",
    "_extract_repo_id",
    "_extract_repo_name",
    "_extract_stars_gained",
    "_parse_count",
    "_parse_trending_repo",
    "_stable_repo_id",
    "handle_twitter_edit_message",
    "handle_twitter_post_callback",
    "parse_trending_repo",
]
