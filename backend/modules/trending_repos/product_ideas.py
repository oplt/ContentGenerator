from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.inference.providers import (
    OpenAICompatibleLLMProvider,
    collect_inference_readiness,
    get_llm_provider,
)
from backend.modules.trending_repos.github_client import GITHUB_REPO_URL
from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.repository import TrendingReposRepository

logger = logging.getLogger(__name__)

MAX_README_PROMPT_CHARS = 6_000
PLACEHOLDER_IDEA_VALUES = {"", "string", "n/a", "unknown", "todo"}


class ProductIdeasGenerator:
    """LLM product-idea generation for trending repos."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: TrendingReposRepository,
        llm: Any | None = None,
        github_headers_builder: Any | None = None,
    ) -> None:
        self.db = db
        self.repo = repo
        self.llm = llm or get_llm_provider()
        self._github_headers_builder = github_headers_builder

    def _build_github_headers(self, accept: str) -> dict[str, str]:
        if self._github_headers_builder:
            return self._github_headers_builder(accept)
        from backend.modules.trending_repos.github_client import GitHubTrendingClient
        return GitHubTrendingClient()._build_github_headers(accept)

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

    def _get_product_ideas_llm(self) -> Any:
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

    async def _get_llm_provider_health(self, provider_name: str) -> Any:
        if provider_name in {"ollama", "vllm", "llamacpp"}:
            readiness = await collect_inference_readiness()
            return readiness[provider_name]
        if provider_name in {"openai", "openai_compatible"}:
            return await OpenAICompatibleLLMProvider(provider_name="openai_compatible").healthcheck()
        return await get_llm_provider(provider_name).healthcheck()

    async def _fetch_repo_readme_excerpt(self, full_name: str) -> str | None:
        try:
            async with shared_http_client() as client:
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
        await self.db.flush()
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
    # Twitter post Telegram callback handling
    # ------------------------------------------------------------------

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
    ideas_value = result.get("ideas")
    ideas_list = ideas_value if isinstance(ideas_value, list) else []

    payload = {
        "keys": sorted(str(key) for key in result.keys()),
        "repo_assessment_type": type(result.get("repo_assessment")).__name__,
        "ideas_type": type(ideas_value).__name__,
        "ideas_count": len(ideas_list) if ideas_list else None,
        "first_idea_keys": (
            sorted(str(key) for key in result["ideas"][0].keys())
            if ideas_list
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
