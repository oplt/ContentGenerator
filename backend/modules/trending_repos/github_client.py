from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from backend.core.config import settings
from backend.core.http import shared_http_client

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

STAR_GAIN_PATTERN = re.compile(
    r"([\d.,]+[kmb]?)\s+stars?\s+(today|this week|this month)", re.IGNORECASE
)
REPO_ID_PATTERN = re.compile(r'"repository_id":\s*(\d+)')


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
        from backend.core.http import get_http_client

        client = await get_http_client()
        resp = await client.get(
            GITHUB_TRENDING_URL,
            headers=self._build_github_headers("text/html,application/xhtml+xml"),
            params={"since": period},
            timeout=15.0,
        )
        resp.raise_for_status()
        repos = self._parse_trending_html(resp.text)

        if getattr(settings, "GITHUB_TOKEN", None):
            repos = await self._enrich_trending_repos(client, repos)

        return repos

    async def _fetch_from_github_search(self, period: str) -> list[dict[str, Any]]:
        """
        Fetch fallback trending repos from GitHub Search API.

        Trending = repos created in the last N days, sorted by stars descending.
        This is a reliable proxy: high-star repos in a short creation window
        are genuinely going viral.
        """
        from backend.core.http import get_http_client

        days = PERIOD_DAYS.get(period, 1)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"created:>{since}"

        params: dict[str, str | int] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": MAX_REPOS,
        }

        client = await get_http_client()
        resp = await client.get(
            GITHUB_SEARCH_URL,
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
            repo = _parse_trending_repo(article)
            if repo is None or repo["full_name"] in seen:
                continue
            repos.append(repo)
            seen.add(repo["full_name"])
            if len(repos) >= MAX_REPOS:
                break

        return repos

    async def _enrich_trending_repos(
        self, client: httpx.AsyncClient, repos: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Enrich repos via GitHub API with bounded concurrency; keep partial successes."""
        from backend.core.config import settings as app_settings
        from backend.core.http import map_concurrent

        async def _enrich_one(repo: dict[str, Any]) -> dict[str, Any]:
            try:
                resp = await client.get(
                    f"{GITHUB_REPO_URL}/{repo['full_name']}",
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

def _parse_trending_repo(article: Any) -> dict[str, Any] | None:
    link = article.select_one("h2 a[href]")
    full_name = _extract_repo_name(link)
    if not full_name:
        return None

    description_el = article.select_one("p")
    language_el = article.select_one('[itemprop="programmingLanguage"]')
    stars_el = article.select_one(f'a[href="/{full_name}/stargazers"]')
    forks_el = article.select_one(f'a[href="/{full_name}/forks"]')
    article_text = article.get_text(" ", strip=True)

    stars_count = _parse_count(stars_el.get_text(" ", strip=True) if stars_el else "")
    forks_count = _parse_count(forks_el.get_text(" ", strip=True) if forks_el else "")
    stars_gained = _extract_stars_gained(article_text)
    github_id = _extract_repo_id(str(article)) or _stable_repo_id(full_name)

    return {
        "github_id": github_id,
        "name": full_name,
        "full_name": full_name,
        "description": description_el.get_text(" ", strip=True) or None if description_el else None,
        "html_url": f"https://github.com/{full_name}",
        "language": language_el.get_text(" ", strip=True) or None if language_el else None,
        "topics": [],
        "stars_count": stars_count,
        "forks_count": forks_count,
        "watchers_count": stars_count,
        "open_issues_count": 0,
        "stars_gained": stars_gained,
    }


def _extract_repo_name(link: Any) -> str | None:
    href = (link.get("href") if link else "") or ""
    full_name = href.strip().strip("/")
    if not full_name or "/" not in full_name:
        return None
    owner, repo = full_name.split("/", 1)
    return f"{owner.strip()}/{repo.strip()}"


def _extract_repo_id(article_html: str) -> int:
    match = REPO_ID_PATTERN.search(article_html)
    return int(match.group(1)) if match else 0


def _extract_stars_gained(article_text: str) -> int:
    match = STAR_GAIN_PATTERN.search(article_text)
    if not match:
        return 0
    return _parse_count(match.group(1))


def _parse_count(raw: str) -> int:
    cleaned = raw.strip().lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)([kmb]?)", cleaned)
    if not match:
        return 0

    value = float(match.group(1))
    multiplier = {
        "": 1,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }[match.group(2)]
    return int(value * multiplier)


def _stable_repo_id(full_name: str) -> int:
    # GitHub Trending markup does not consistently expose a repo id. Use a
    # deterministic fallback so snapshots remain stable when API enrichment is off.
    return int(hashlib.sha1(full_name.encode("utf-8")).hexdigest()[:12], 16)


# ---------------------------------------------------------------------------
# Telegram callback handlers (module-level, called from approvals router)
# ---------------------------------------------------------------------------

async def handle_twitter_post_callback(
    callback_query: dict,
    db: "AsyncSession",
) -> None:
    """
    Handle tw_post / tw_edit / tw_reject inline button callbacks from Telegram.
    Always calls answerCallbackQuery to dismiss the loading spinner.
    """
    import json as _json
    from backend.core.cache import redis_client
    from backend.modules.approvals.providers import (
        TelegramProvider,
        get_telegram_provider,
        verify_signed_callback_data,
    )

    callback_data: str = callback_query.get("data", "")
    callback_query_id: str = str(callback_query.get("id", ""))
    # chat_id from the incoming message (used for edit session key)
    incoming_chat_id: str = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
    message_id: str = str(callback_query.get("message", {}).get("message_id", ""))

    valid, action, post_id = verify_signed_callback_data(callback_data)

    redis_key = f"twitter_post:{post_id}" if post_id else ""
    raw = await redis_client.get(redis_key) if redis_key else None

    if not raw:
        # Try to answer using a raw API call if we can't build a provider
        if valid and not raw:
            # expired or already handled — best-effort answer via httpx
            import httpx as _httpx
            from backend.core.config import settings as _settings
            # We can't do much without the bot token, log and return
            logger.warning("Twitter post callback: Redis key missing for post_id=%s", post_id)
        return

    stored = _json.loads(raw)
    tenant_id = uuid.UUID(stored["tenant_id"])
    post_text: str = stored["post_text"]
    repo_name: str = stored.get("repo_full_name", "")
    repo_url: str = stored.get("repo_url", "")
    bot_token: str = stored.get("bot_token", "")
    chat_id: str = stored.get("chat_id", incoming_chat_id)

    provider = get_telegram_provider(bot_token=bot_token, chat_id=chat_id)

    if not valid:
        await provider.answer_callback(callback_query_id, "⚠️ Invalid request signature.")
        return

    if action == "tw_post":
        await redis_client.delete(redis_key)
        try:
            svc = TrendingReposService(db)
            await svc._post_to_twitter_for_tenant(tenant_id, post_text)
            await provider.answer_callback(callback_query_id, "✅ Posted to Twitter!")
            await provider.edit_message(
                chat_id=chat_id,
                message_id=message_id,
                new_text=f"<b>✅ Posted to Twitter</b>\n\n{post_text}",
            )
        except Exception as exc:
            logger.exception("Failed to post to Twitter from Telegram callback")
            await provider.answer_callback(callback_query_id, f"❌ Failed: {str(exc)[:200]}")

    elif action == "tw_reject":
        await redis_client.delete(redis_key)
        await provider.answer_callback(callback_query_id, "❌ Post rejected.")
        await provider.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            new_text=f"<b>❌ Rejected</b>\n\n<s>{post_text}</s>",
        )

    elif action == "tw_edit":
        edit_session_key = f"twitter_post:edit_session:{incoming_chat_id}"
        await redis_client.set(edit_session_key, post_id, ex=3600)
        await provider.answer_callback(callback_query_id, "✏️ Send your updated post text now.")


async def handle_twitter_edit_message(
    payload: dict,
    db: "AsyncSession",
) -> bool:
    """
    If a Twitter edit session is active for this chat, apply the incoming message
    as the new post text and re-send the card with updated content.
    Returns True if the message was consumed.
    """
    import json as _json
    from backend.core.cache import redis_client
    from backend.modules.approvals.providers import get_telegram_provider
    from backend.modules.settings.service import SettingsService

    message = payload.get("message", {})
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not text or not chat_id:
        return False

    edit_session_key = f"twitter_post:edit_session:{chat_id}"
    post_id = await redis_client.get(edit_session_key)
    if not post_id:
        return False

    redis_key = f"twitter_post:{post_id}"
    raw = await redis_client.get(redis_key)
    if not raw:
        await redis_client.delete(edit_session_key)
        return False

    stored = _json.loads(raw)
    tenant_id = uuid.UUID(stored["tenant_id"])
    repo_name: str = stored.get("repo_full_name", "")
    repo_url: str = stored.get("repo_url", "")

    # Update stored post text
    stored["post_text"] = text
    await redis_client.set(redis_key, _json.dumps(stored), ex=86400)
    await redis_client.delete(edit_session_key)

    # Re-send the card with the new text
    svc_settings = SettingsService(db)
    config = await svc_settings.resolve_telegram_runtime_config(tenant_id)
    bot_token = str(config.get("bot_token") or "")
    telegram_chat_id = str(config.get("chat_id") or "")
    provider = get_telegram_provider(bot_token=bot_token, chat_id=telegram_chat_id)
    await provider.send_twitter_post_card(
        repo_name=repo_name,
        repo_url=repo_url,
        post_text=text,
        post_id=post_id,
    )
    return True

