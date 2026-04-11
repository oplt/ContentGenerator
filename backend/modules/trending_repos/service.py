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
from backend.modules.inference.providers import (
    OpenAICompatibleLLMProvider,
    collect_inference_readiness,
)
from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.repository import TrendingReposRepository
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

    # ------------------------------------------------------------------
    # GitHub fetching
    # ------------------------------------------------------------------

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
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                GITHUB_TRENDING_URL,
                headers=self._build_github_headers("text/html,application/xhtml+xml"),
                params={"since": period},
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
        days = PERIOD_DAYS.get(period, 1)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"created:>{since}"

        params: dict[str, str | int] = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": MAX_REPOS,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                GITHUB_SEARCH_URL,
                headers=self._build_github_headers("application/vnd.github+json"),
                params=params,
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
        enriched: list[dict[str, Any]] = []
        for repo in repos:
            try:
                resp = await client.get(
                    f"{GITHUB_REPO_URL}/{repo['full_name']}",
                    headers=self._build_github_headers("application/vnd.github+json"),
                )
                resp.raise_for_status()
                details = resp.json()
            except Exception:
                logger.warning(
                    "Failed to enrich trending repo %s from GitHub API", repo["full_name"]
                )
                enriched.append(repo)
                continue

            enriched.append(
                {
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
            )

        return enriched

    # ------------------------------------------------------------------
    # Snapshot persistence
    # ------------------------------------------------------------------

    async def refresh_snapshot(self, tenant_id: uuid.UUID, period: str) -> list[TrendingRepo]:
        today = date.today()
        raw = await self.fetch_from_github(period)
        records = await self.repo.upsert_snapshot(tenant_id, period, today, raw)
        await self.db.commit()
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
        prompt_path = (
            Path(__file__).resolve().parents[2] / "prompts" / "product_hunter" / "v1" / "system.md"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        return _FALLBACK_PRODUCT_HUNTER_PROMPT

    # def _get_product_ideas_llm(self) -> OpenAICompatibleLLMProvider:
    #     if not settings.LLM_BASE_URL:
    #         raise RuntimeError(
    #             "Generate Ideas requires a ChatGPT/OpenAI-compatible API connection. "
    #             "Configure LLM_BASE_URL and LLM_API_KEY in the backend environment."
    #         )
    #     return OpenAICompatibleLLMProvider(provider_name="openai_compatible")

    def _get_product_ideas_llm(self):
        if not settings.LLM_PROVIDER:
            raise RuntimeError(
                "Generate Ideas requires a local LLM model. "
                "Configure LLM_PROVIDER in the backend environment."
            )
        return get_llm_provider(settings.LLM_PROVIDER)

    async def _ensure_product_ideas_llm_ready(self) -> None:
        provider_name = str(settings.LLM_PROVIDER or "mock").strip().lower() or "mock"
        if provider_name == "mock":
            return

        health = await self._get_llm_provider_health(provider_name)
        if health.ready:
            return

        raise RuntimeError(
            f"Generate Ideas LLM provider '{provider_name}' is unavailable: {health.detail}. "
            "Start the configured LLM service or update LLM_PROVIDER to a reachable provider."
        )

    async def _get_llm_provider_health(self, provider_name: str):
        if provider_name in {"ollama", "vllm", "llamacpp"}:
            readiness = await collect_inference_readiness()
            return readiness[provider_name]
        if provider_name in {"openai", "openai_compatible"}:
            return await OpenAICompatibleLLMProvider(provider_name="openai_compatible").healthcheck()
        return await get_llm_provider(provider_name).healthcheck()

    async def _fetch_repo_readme_excerpt(self, full_name: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{GITHUB_REPO_URL}/{full_name}/readme",
                    headers=self._build_github_headers("application/vnd.github.raw"),
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Failed to fetch README for repo %s; generating ideas without README", full_name)
            return None

        text = response.text.strip()
        if not text:
            return None
        return text[:MAX_README_PROMPT_CHARS]

    async def generate_product_ideas(
        self, tenant_id: uuid.UUID, repo_id: uuid.UUID
    ) -> TrendingRepo:
        record = await self.repo.get_by_id(tenant_id, repo_id)
        if record is None:
            raise ValueError(f"TrendingRepo {repo_id} not found for tenant {tenant_id}")

        llm = self._get_product_ideas_llm()
        await self._ensure_product_ideas_llm_ready()
        system_prompt = self._load_product_hunter_prompt()
        readme_excerpt = await self._fetch_repo_readme_excerpt(record.full_name)
        user_prompt = _build_ideas_prompt(record, readme_excerpt=readme_excerpt)
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        schema_hint = {
            "repo_assessment": {
                "what_it_does": "string",
                "evidence": ["string"],
                "strongest_assets": ["string"],
                "main_limitations": ["string"],
                "best_commercial_angle": "string",
                "confidence": "medium",
            },
            "ideas": [
                {
                    "rank": 1,
                    "title": "string",
                    "positioning": "string",
                    "target_customer": "string",
                    "pain_point": "string",
                    "product_concept": "string",
                    "why_this_repo_fits": "string",
                    "required_extensions": ["string"],
                    "monetization": {
                        "model": "string",
                        "pricing_logic": "string",
                        "estimated_willingness_to_pay": "string",
                    },
                    "scores": {
                        "revenue_potential": 0,
                        "customer_urgency": 0,
                        "repo_leverage": 0,
                        "speed_to_mvp": 0,
                        "competitive_intensity": 0,
                    },
                    "time_to_mvp": "string",
                    "key_risks": ["string"],
                    "why_now": "string",
                    "investor_angle": "string",
                    "v1_scope": ["string"],
                    "not_for_v1": ["string"],
                }
            ],
        }

        result = await llm.generate_structured_json(
            full_prompt,
            schema_hint=schema_hint,
            max_tokens=8192,
            temperature=0.2,
            task="product_hunter",
        )

        repo_assessment = _normalize_repo_assessment(result.get("repo_assessment"))
        ideas = _normalize_generated_ideas(result.get("ideas") or [])
        if not ideas:
            logger.warning(
                "Product hunter returned unusable structured output for repo %s (%s): %s",
                record.name,
                repo_id,
                _format_product_hunter_result_preview(result),
            )
            raise RuntimeError(
                "Idea generation returned unusable output. No ideas were saved."
            )
        record.repo_assessment = repo_assessment
        record.product_ideas = ideas
        record.ideas_generated_at = datetime.now(timezone.utc)
        await self.repo.save(record)
        await self.db.commit()
        logger.info(
            "Generated %d product ideas for repo %s (%s)",
            len(ideas),
            record.name,
            repo_id,
        )
        return record

    async def generate_ideas_for_daily_snapshot(self, tenant_id: uuid.UUID) -> list[TrendingRepo]:
        """Generate product ideas for today's daily snapshot — called by Celery."""
        records = await self.repo.get_latest_by_period(tenant_id, "daily")
        updated = []
        for record in records:
            try:
                updated_record = await self.generate_product_ideas(tenant_id, record.id)
                updated.append(updated_record)
            except Exception:
                logger.exception("Failed to generate ideas for repo %s", record.name)
        return updated

    # ------------------------------------------------------------------
    # Telegram notifications
    # ------------------------------------------------------------------

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


def _build_ideas_prompt(record: TrendingRepo, *, readme_excerpt: str | None = None) -> str:
    topics = ", ".join(record.topics[:8]) if record.topics else "N/A"
    readme_section = (
        f"\nREADME excerpt:\n{readme_excerpt}\n" if readme_excerpt else "\nREADME excerpt: N/A\n"
    )
    return (
        f"GitHub repository: **{record.full_name}**\n"
        f"Description: {record.description or 'N/A'}\n"
        f"Language: {record.language or 'N/A'}\n"
        f"Topics: {topics}\n"
        f"Stars: {record.stars_count:,} (gained {record.stars_gained:,} in this period)\n"
        f"URL: {record.html_url}\n"
        f"{readme_section}\n"
        "CRITICAL INSTRUCTION: You MUST return ONLY a valid JSON object. "
        "Do not include any explanatory text, markdown formatting, or code blocks. "
        "Do not wrap the JSON in ```json or ``` tags. Just raw JSON.\n\n"
        "Using the repository metadata and README content above, generate exactly 5 of the most valuable "
        "product ideas that could realistically be built from this repo's capabilities. "
        "Prioritize ideas with clear customer demand, revenue potential, and a strong wedge to market. "
        "Return valid JSON matching the Product Hunter output schema, including repo_assessment "
        "and the full ranked ideas objects.\n\n"
        "EXPECTED JSON STRUCTURE:\n"
        "{\n"
        '  "repo_assessment": {\n'
        '    "what_it_does": "string",\n'
        '    "evidence": ["string"],\n'
        '    "strongest_assets": ["string"],\n'
        '    "main_limitations": ["string"],\n'
        '    "best_commercial_angle": "string",\n'
        '    "confidence": "high|medium|low"\n'
        "  },\n"
        '  "ideas": [\n'
        "    {\n"
        '      "rank": 1,\n'
        '      "title": "string",\n'
        '      "positioning": "string",\n'
        '      "target_customer": "string",\n'
        '      "pain_point": "string",\n'
        '      "product_concept": "string",\n'
        '      "why_this_repo_fits": "string",\n'
        '      "required_extensions": ["string"],\n'
        '      "monetization": {\n'
        '        "model": "string",\n'
        '        "pricing_logic": "string",\n'
        '        "estimated_willingness_to_pay": "string"\n'
        "      },\n"
        '      "scores": {\n'
        '        "revenue_potential": 0,\n'
        '        "customer_urgency": 0,\n'
        '        "repo_leverage": 0,\n'
        '        "speed_to_mvp": 0,\n'
        '        "competitive_intensity": 0\n'
        "      },\n"
        '      "time_to_mvp": "string",\n'
        '      "key_risks": ["string"],\n'
        '      "why_now": "string",\n'
        '      "investor_angle": "string",\n'
        '      "v1_scope": ["string"],\n'
        '      "not_for_v1": ["string"]\n'
        "    }\n"
        "  ]\n"
        "}"
    )


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


def _normalize_repo_assessment(raw_assessment: Any) -> dict[str, Any] | None:
    if not isinstance(raw_assessment, dict):
        return None

    assessment = {
        "what_it_does": _stringify_idea_value(raw_assessment.get("what_it_does")),
        "evidence": _normalize_text_list(raw_assessment.get("evidence")),
        "strongest_assets": _normalize_text_list(raw_assessment.get("strongest_assets")),
        "main_limitations": _normalize_text_list(raw_assessment.get("main_limitations")),
        "best_commercial_angle": _stringify_idea_value(raw_assessment.get("best_commercial_angle")),
        "confidence": _normalize_confidence(raw_assessment.get("confidence")),
    }
    if not any(
        [
            assessment["what_it_does"],
            assessment["evidence"],
            assessment["strongest_assets"],
            assessment["main_limitations"],
            assessment["best_commercial_angle"],
        ]
    ):
        return None
    return assessment


def _normalize_generated_ideas(raw_ideas: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_ideas, list):
        return []

    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_ideas, start=1):
        if not isinstance(item, dict):
            continue
        idea = {
            "rank": _normalize_rank(item.get("rank"), idx),
            "title": _pick_idea_text(item, "title"),
            "positioning": _pick_idea_text(item, "positioning", "wow_factor"),
            "target_customer": _pick_idea_text(item, "target_customer", "target_audience"),
            "pain_point": _pick_idea_text(item, "pain_point", "problem"),
            "product_concept": _pick_idea_text(item, "product_concept", "solution"),
            "why_this_repo_fits": _pick_idea_text(item, "why_this_repo_fits"),
            "required_extensions": _normalize_text_list(item.get("required_extensions")),
            "monetization": _normalize_monetization(item.get("monetization")),
            "scores": _normalize_scores(item.get("scores")),
            "time_to_mvp": _pick_idea_text(item, "time_to_mvp"),
            "key_risks": _normalize_text_list(item.get("key_risks")),
            "why_now": _pick_idea_text(item, "why_now"),
            "investor_angle": _pick_idea_text(item, "investor_angle"),
            "v1_scope": _normalize_text_list(item.get("v1_scope")),
            "not_for_v1": _normalize_text_list(item.get("not_for_v1")),
        }
        if _is_placeholder_idea(idea):
            continue
        normalized.append(idea)
    return normalized


def _pick_idea_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        text = _stringify_idea_value(value)
        if text:
            return text
    return ""


def _stringify_idea_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    if isinstance(value, dict):
        parts = [_stringify_idea_value(part) for part in value.values()]
        return "; ".join(part for part in parts if part)
    if isinstance(value, list):
        parts = [_stringify_idea_value(part) for part in value]
        return "; ".join(part for part in parts if part)
    return str(value).strip()


def _normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _stringify_idea_value(item))]
    text = _stringify_idea_value(value)
    return [text] if text else []


def _normalize_confidence(value: Any) -> str:
    normalized = _stringify_idea_value(value).lower()
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "medium"


def _normalize_rank(value: Any, fallback: int) -> int:
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return fallback
    return rank if rank > 0 else fallback


def _normalize_monetization(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "model": _stringify_idea_value(value.get("model")),
            "pricing_logic": _stringify_idea_value(value.get("pricing_logic")),
            "estimated_willingness_to_pay": _stringify_idea_value(
                value.get("estimated_willingness_to_pay")
            ),
        }
    text = _stringify_idea_value(value)
    return {
        "model": text,
        "pricing_logic": "",
        "estimated_willingness_to_pay": "",
    }


def _normalize_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 10))


def _normalize_scores(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        value = {}
    return {
        "revenue_potential": _normalize_score(value.get("revenue_potential")),
        "customer_urgency": _normalize_score(value.get("customer_urgency")),
        "repo_leverage": _normalize_score(value.get("repo_leverage")),
        "speed_to_mvp": _normalize_score(value.get("speed_to_mvp")),
        "competitive_intensity": _normalize_score(value.get("competitive_intensity")),
    }


def _format_product_hunter_result_preview(result: Any) -> str:
    if not isinstance(result, dict):
        return f"type={type(result).__name__}"

    payload = {
        "keys": sorted(str(key) for key in result.keys()),
        "repo_assessment_type": type(result.get("repo_assessment")).__name__,
        "ideas_type": type(result.get("ideas")).__name__,
        "ideas_count": len(result.get("ideas")) if isinstance(result.get("ideas"), list) else None,
        "first_idea_keys": (
            sorted(str(key) for key in result["ideas"][0].keys())
            if isinstance(result.get("ideas"), list)
            and result["ideas"]
            and isinstance(result["ideas"][0], dict)
            else []
        ),
        "preview": _stringify_idea_value(result)[:800],
    }
    return json.dumps(payload, ensure_ascii=True)


def _is_placeholder_idea(idea: dict[str, Any]) -> bool:
    values = [
        _stringify_idea_value(idea.get("title")).strip().lower(),
        _stringify_idea_value(idea.get("positioning")).strip().lower(),
        _stringify_idea_value(idea.get("target_customer")).strip().lower(),
        _stringify_idea_value(idea.get("pain_point")).strip().lower(),
        _stringify_idea_value(idea.get("product_concept")).strip().lower(),
    ]
    non_empty = [value for value in values if value]
    if not non_empty:
        return True
    return all(value in PLACEHOLDER_IDEA_VALUES for value in non_empty)


_FALLBACK_PRODUCT_HUNTER_PROMPT = """\
You are an expert Product Hunter with 15+ years of experience identifying breakthrough \
technology products. You have a sharp eye for market gaps, underserved audiences, and \
developer tools that can become billion-dollar businesses. You combine technical depth \
with product intuition — you understand both what engineers build and what users pay for.

When analyzing a GitHub repository, you think about:
- The core technical innovation and what makes it unique
- Real pain points it solves (or could solve with a product wrapper)
- Which audience segments would pay money for this
- How to monetize it (SaaS, API, marketplace, enterprise license, etc.)
- The "wow factor" — what makes someone say "I need this NOW"

You generate bold, concrete, and specific product ideas — not vague suggestions. \
Each idea is something a small team could ship in 3-6 months and get paying customers within a year.
"""


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
