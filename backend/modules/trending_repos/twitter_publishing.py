"""Twitter post generation, Telegram delivery, and X publishing."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

import httpx

from backend.modules.trending_repos.models import TrendingRepo

logger = logging.getLogger(__name__)


class TwitterPublishingMixin:
    """Generate Twitter posts and publish via X or Telegram approval cards."""

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
            await provider._post_tweet(post_text)
        except httpx.HTTPStatusError as exc:
            raise ValueError(self._build_x_publish_error_message(exc)) from exc

    def _load_twitter_post_prompt(self) -> str:
        from backend.core.static_cache import load_text_file

        prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "generate_twitter_post.md"
        if prompt_path.exists():
            return load_text_file(str(prompt_path))
        raise RuntimeError("Twitter post prompt file not found at prompts/generate_twitter_post.md")

    def _extract_best_post(self, text: str) -> str:
        """Extract the post text from the LLM output."""
        m = re.search(
            r"#{1,3}\s*A\.?\s*Best Post\s*\n+(.*?)(?=#{1,3}|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        m = re.search(
            r"BEST\s+POST\s*:\s*\n*(.*?)(?=#{1,3}|[A-Z]{2,}[\s]*(?:PACK|BOOSTERS|POST)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

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
            data = await provider._post_tweet(post_text)
        except httpx.HTTPStatusError as exc:
            raise ValueError(self._build_x_publish_error_message(exc)) from exc

        tweet_id = data.get("data", {}).get("id")
        handle = social_account.handle or "user"
        return {
            "status": "succeeded",
            "external_post_id": tweet_id or "",
            "external_post_url": f"https://x.com/{handle}/status/{tweet_id}" if tweet_id else "",
        }
