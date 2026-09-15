"""Daily Telegram digest for trending repos and product ideas."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.schemas import TrendingRepoResponse
from backend.modules.trending_repos.idea_normalization import (
    normalize_generated_ideas,
    normalize_repo_assessment,
)

logger = logging.getLogger(__name__)


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


def serialize_trending_repo_response(record: TrendingRepo) -> TrendingRepoResponse:
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
        "repo_assessment": normalize_repo_assessment(getattr(record, "repo_assessment", None)),
        "product_ideas": normalize_generated_ideas(getattr(record, "product_ideas", [])),
        "ideas_generated_at": record.ideas_generated_at,
        "created_at": record.created_at,
    }
    return TrendingRepoResponse.model_validate(payload)


class TelegramDigestMixin:
    """Send daily trending digest messages to Telegram."""

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

        today = escape_md(date.today().isoformat())
        lines = [f"*🔥 Trending GitHub Repos — {today}*\n"]

        for r in records[:10]:
            lang = f" · {escape_md(r.language)}" if r.language else ""
            lines.append(
                f"{r.rank}\\. [{escape_md(r.name)}]({r.html_url}) "
                f"⭐ {r.stars_count:,}{lang}\n"
                f"   _{escape_md(r.description or 'No description')}_\n"
            )

        ideas_lines: list[str] = []
        for r in records[:5]:
            if r.product_ideas:
                ideas_lines.append(f"\n*💡 Ideas from [{escape_md(r.name)}]({r.html_url})*")
                for idx, idea in enumerate(r.product_ideas[:2], start=1):
                    title = idea.get("title", "")
                    positioning = str(idea.get("positioning") or idea.get("wow_factor") or "")
                    ideas_lines.append(
                        f"  {idx}\\. *{escape_md(title)}* — {escape_md(positioning)}"
                    )

        message = "\n".join(lines + ideas_lines)

        await provider.send_message(message, parse_mode="MarkdownV2")
        logger.info(
            "Sent daily trending digest to Telegram for tenant %s (%d repos)",
            tenant_id,
            len(records),
        )


# Historical private-name aliases.
_escape_md = escape_md
_serialize_trending_repo_response = serialize_trending_repo_response
