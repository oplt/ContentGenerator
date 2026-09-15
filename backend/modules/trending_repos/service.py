from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.http import shared_http_client
from backend.modules.inference.providers import (
    OpenAICompatibleLLMProvider,
    collect_inference_readiness,
)
from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.repository import TrendingReposRepository
from backend.modules.trending_repos.github_client import GitHubTrendingClient
from backend.modules.trending_repos.product_ideas import ProductIdeasGenerator
from backend.modules.trending_repos.schemas import TrendingRepoResponse, TrendingReposListResponse
from backend.modules.inference.providers import get_llm_provider

logger = logging.getLogger(__name__)

# GitHub does not expose an official Trending API. We prefer the public Trending
# HTML page for rank parity and fall back to Search API when scraping fails.
GITHUB_TRENDING_URL = "https://github.com/trending"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_REPO_URL = "https://api.github.com/repos"
MAX_README_PROMPT_CHARS = 6_000

PERIOD_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}

# Maximum repos to fetch per snapshot
MAX_REPOS = 25
PLACEHOLDER_IDEA_VALUES = {"", "string", "n/a", "unknown", "todo"}

STAR_GAIN_PATTERN = re.compile(
    r"([\d.,]+[kmb]?)\s+stars?\s+(today|this week|this month)", re.IGNORECASE
)
REPO_ID_PATTERN = re.compile(r'"repository_id":\s*(\d+)')


class TrendingReposService:
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

    # ------------------------------------------------------------------
    # GitHub fetching
    # ------------------------------------------------------------------

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
        self, client: httpx.AsyncClient, repos: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return await self.github._enrich_trending_repos(client, repos)

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
            repos=[_serialize_trending_repo_response(r) for r in records],
            period=period,
            snapshot_date=snapshot_date,
            total=len(records),
        )

    # ------------------------------------------------------------------
    # Product idea generation
    # ------------------------------------------------------------------

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

    def _build_x_publish_error_message(self, exc: httpx.HTTPStatusError) -> str:
        status_code = exc.response.status_code
        detail = ""
        try:
            payload = exc.response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            detail = str(
                payload.get("detail")
                or payload.get("title")
                or (
                    payload["errors"][0].get("message")
                    if isinstance(payload.get("errors"), list) and payload["errors"]
                    else ""
                )
            ).strip()

        if status_code == 401:
            return (
                "X rejected the stored access token. Open Settings -> Social Accounts -> Twitter "
                "and save a valid OAuth 2.0 user access token."
            )

        if status_code == 403:
            suffix = f" X says: {detail}." if detail else ""
            return (
                "X refused to create the tweet. Save an OAuth 2.0 user access token for the same "
                "account with `tweet.write` and `users.read` scopes, and make sure the X app has "
                "Read and Write permissions. App-only bearer tokens cannot post tweets."
                f"{suffix}"
            )

        if detail:
            return f"X API error ({status_code}): {detail}"
        return f"X API error ({status_code})."

    async def _post_to_twitter_for_tenant(self, tenant_id: uuid.UUID, post_text: str) -> None:
        """Internal: post text to Twitter on behalf of tenant. Raises on failure."""
        from backend.core.security import decrypt_secret, resolve_secret_reference
        from backend.modules.publishing.providers import XPublishingProvider
        from backend.modules.publishing.repository import PublishingRepository
        import httpx

        pub_repo = PublishingRepository(self.db)
        social_account = await pub_repo.get_social_account_by_platform(tenant_id, "x")
        if not social_account:
            raise ValueError("No Twitter account configured. Add one in Settings → Social Accounts.")

        if social_account.account_metadata.get("mode") != "real":
            raise ValueError(
                "Twitter account is in Stub mode. Switch to Manual / Live in Settings to post for real."
            )

        token_row = await pub_repo.get_token_for_account(social_account.id)
        access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
        if access_token.startswith("secret-ref:"):
            access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""
        if not access_token:
            raise ValueError(
                "No access token stored. Re-open Twitter settings and save with a valid access token."
            )

        provider = XPublishingProvider(access_token=access_token, dry_run=False)
        try:
            async with shared_http_client() as client:
                await provider._post_tweet(client, post_text)
        except httpx.HTTPStatusError as exc:
            raise ValueError(self._build_x_publish_error_message(exc)) from exc

    # ------------------------------------------------------------------
    # Telegram notifications
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Twitter post generation
    # ------------------------------------------------------------------

    def _load_twitter_post_prompt(self) -> str:
        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "generate_twitter_post.md"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        raise RuntimeError("Twitter post prompt file not found at prompts/generate_twitter_post.md")

    def _extract_best_post(self, text: str) -> str:
        """Extract the post text from the LLM output.

        Tries to pull the content under '### A. Best Post' or 'BEST POST:'.
        Falls back to the full output stripped of obvious section headers.
        """
        import re

        # Try markdown header: ### A. Best Post
        m = re.search(
            r"#{1,3}\s*A\.?\s*Best Post\s*\n+(.*?)(?=#{1,3}|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        # Try plain label: BEST POST:
        m = re.search(
            r"BEST\s+POST\s*:\s*\n*(.*?)(?=#{1,3}|[A-Z]{2,}[\s]*(?:PACK|BOOSTERS|POST)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        # Fallback: return the whole output as-is
        return text.strip()

    async def generate_twitter_post(
        self, tenant_id: uuid.UUID, repo_id: uuid.UUID
    ) -> str:
        record = await self.repo.get_by_id(tenant_id, repo_id)
        if record is None:
            raise ValueError(f"TrendingRepo {repo_id} not found for tenant {tenant_id}")

        system_prompt = self._load_twitter_post_prompt()
        topics = ", ".join(record.topics[:8]) if record.topics else "N/A"
        user_prompt = (
            f"Repository name: {record.full_name}\n"
            f"GitHub URL: {record.html_url}\n"
            f"Description: {record.description or 'N/A'}\n"
            f"Language: {record.language or 'N/A'}\n"
            f"Topics: {topics}\n"
            f"Stars: {record.stars_count:,} (gained {record.stars_gained:,} in this period)\n"
        )

        llm = self._get_product_ideas_llm()
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        raw_text = await llm.generate_text(full_prompt, max_tokens=1024, temperature=0.7)
        post_text = self._extract_best_post(raw_text)

        try:
            await self._send_twitter_post_to_telegram(tenant_id, record, post_text)
        except Exception:
            logger.exception("Failed to send Twitter post to Telegram for repo %s", record.name)

        return post_text

    async def _send_twitter_post_to_telegram(
        self,
        tenant_id: uuid.UUID,
        record: TrendingRepo,
        post_text: str,
    ) -> None:
        import json as _json
        from backend.core.cache import redis_client
        from backend.modules.approvals.providers import get_telegram_provider
        from backend.modules.settings.service import SettingsService

        svc = SettingsService(self.db)
        config = await svc.resolve_telegram_runtime_config(tenant_id)

        bot_token = str(config.get("bot_token") or "")
        chat_id = str(config.get("chat_id") or "")
        enabled = bool(config.get("enabled", False))

        if not enabled or not bot_token or not chat_id:
            logger.info("Telegram not configured for tenant %s — skipping Twitter post", tenant_id)
            return

        post_id = str(uuid.uuid4())
        redis_key = f"twitter_post:{post_id}"
        await redis_client.set(
            redis_key,
            _json.dumps({
                "tenant_id": str(tenant_id),
                "post_text": post_text,
                "repo_full_name": record.full_name,
                "repo_url": record.html_url,
                "bot_token": bot_token,
                "chat_id": chat_id,
            }),
            ex=86400,  # 24h TTL
        )

        provider = get_telegram_provider(bot_token=bot_token, chat_id=chat_id)
        await provider.send_twitter_post_card(
            repo_name=record.full_name,
            repo_url=record.html_url,
            post_text=post_text,
            post_id=post_id,
        )

    async def post_to_twitter(
        self, tenant_id: uuid.UUID, post_text: str
    ) -> dict[str, str]:
        from backend.core.security import decrypt_secret, resolve_secret_reference
        from backend.modules.publishing.providers import XPublishingProvider
        from backend.modules.publishing.repository import PublishingRepository
        import httpx

        pub_repo = PublishingRepository(self.db)
        social_account = await pub_repo.get_social_account_by_platform(tenant_id, "x")
        if not social_account:
            raise ValueError(
                "No Twitter account configured. Add one in Settings → Social Accounts → Twitter."
            )

        if social_account.account_metadata.get("mode") != "real":
            raise ValueError(
                "Twitter account is in Stub mode. Open Settings → Social Accounts → Twitter "
                "and switch to Manual / Live, then save with your access token."
            )

        token_row = await pub_repo.get_token_for_account(social_account.id)
        access_token = decrypt_secret(token_row.access_token_encrypted) if token_row else ""
        if access_token.startswith("secret-ref:"):
            access_token = resolve_secret_reference(access_token.partition(":")[2]) or ""
        if not access_token:
            raise ValueError(
                "No access token found. Re-open Twitter settings and save with a valid access token."
            )

        provider = XPublishingProvider(access_token=access_token, dry_run=False)
        try:
            async with shared_http_client() as client:
                data = await provider._post_tweet(client, post_text)
        except httpx.HTTPStatusError as exc:
            raise ValueError(self._build_x_publish_error_message(exc)) from exc

        tweet_id = data.get("data", {}).get("id")
        handle = social_account.handle or "user"
        return {
            "status": "succeeded",
            "external_post_id": tweet_id or "",
            "external_post_url": f"https://x.com/{handle}/status/{tweet_id}" if tweet_id else "",
        }

    async def send_daily_digest_to_telegram(self, tenant_id: uuid.UUID) -> None:
        """Send today's top trending repos + product ideas to the tenant's Telegram."""
        from backend.modules.approvals.providers import TelegramProvider
        from backend.modules.settings.service import SettingsService

        svc = SettingsService(self.db)
        config = await svc.resolve_telegram_runtime_config(tenant_id)

        bot_token = str(config.get("bot_token") or "")
        chat_id = str(config.get("chat_id") or "")
        enabled = bool(config.get("enabled", False))

        if not enabled or not bot_token or not chat_id:
            logger.info("Telegram not configured for tenant %s — skipping digest", tenant_id)
            return

        provider = TelegramProvider(bot_token=bot_token, chat_id=chat_id)
        records = await self.repo.get_latest_by_period(tenant_id, "daily")

        if not records:
            logger.info("No daily trending repos to send for tenant %s", tenant_id)
            return

        today = _escape_md(date.today().isoformat())
        lines = [f"*🔥 Trending GitHub Repos — {today}*\n"]

        for r in records[:10]:
            lang = f" · {_escape_md(r.language)}" if r.language else ""
            lines.append(
                f"{r.rank}\\. [{_escape_md(r.name)}]({r.html_url}) "
                f"⭐ {r.stars_count:,}{lang}\n"
                f"   _{_escape_md(r.description or 'No description')}_\n"
            )

        # Product ideas section
        ideas_lines: list[str] = []
        for r in records[:5]:
            if r.product_ideas:
                ideas_lines.append(f"\n*💡 Ideas from [{_escape_md(r.name)}]({r.html_url})*")
                for idx, idea in enumerate(r.product_ideas[:2], start=1):
                    title = idea.get("title", "")
                    positioning = str(idea.get("positioning") or idea.get("wow_factor") or "")
                    ideas_lines.append(
                        f"  {idx}\\. *{_escape_md(title)}* — {_escape_md(positioning)}"
                    )

        message = "\n".join(lines + ideas_lines)

        await provider.send_message(message, parse_mode="MarkdownV2")
        logger.info(
            "Sent daily trending digest to Telegram for tenant %s (%d repos)",
            tenant_id,
            len(records),
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


def _serialize_trending_repo_response(record: TrendingRepo) -> TrendingRepoResponse:
    payload = {
        "id": record.id,
        "period": record.period,
        "snapshot_date": record.snapshot_date,
        "github_id": record.github_id,
        "name": record.name,
        "full_name": record.full_name,
        "description": record.description,
        "html_url": record.html_url,
        "language": record.language,
        "topics": record.topics,
        "stars_count": record.stars_count,
        "forks_count": record.forks_count,
        "watchers_count": record.watchers_count,
        "open_issues_count": record.open_issues_count,
        "stars_gained": record.stars_gained,
        "rank": record.rank,
        "repo_assessment": _normalize_repo_assessment(getattr(record, "repo_assessment", None)),
        "product_ideas": _normalize_generated_ideas(getattr(record, "product_ideas", [])),
        "ideas_generated_at": record.ideas_generated_at,
        "created_at": record.created_at,
    }
    return TrendingRepoResponse.model_validate(payload)




# Compatibility re-exports for helpers historically defined in this module.
from backend.modules.trending_repos.github_client import (  # noqa: E402
    PERIOD_DAYS,
    REPO_ID_PATTERN,
    STAR_GAIN_PATTERN,
    _extract_repo_id,
    _extract_repo_name,
    _extract_stars_gained,
    _parse_count,
    _parse_trending_repo,
    _stable_repo_id,
)
from backend.modules.trending_repos.product_ideas import (  # noqa: E402
    PLACEHOLDER_IDEA_VALUES,
    _FALLBACK_PRODUCT_HUNTER_PROMPT,
    _build_ideas_prompt,
    _format_product_hunter_result_preview,
    _is_placeholder_idea,
    _normalize_generated_ideas,
    _normalize_repo_assessment,
)


async def handle_twitter_edit_message(
    payload: dict[str, Any],
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
