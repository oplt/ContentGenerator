"""LLM product-idea generation for trending repos."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.http import request
from backend.modules.inference.providers import (
    OpenAICompatibleLLMProvider,
    collect_inference_readiness,
    get_llm_provider,
)
from backend.modules.trending_repos.github_client import GITHUB_REPO_URL
from backend.modules.trending_repos.idea_normalization import (
    PLACEHOLDER_IDEA_VALUES,
    format_product_hunter_result_preview,
    normalize_generated_ideas,
    normalize_repo_assessment,
    _format_product_hunter_result_preview,
    _is_placeholder_idea,
    _normalize_generated_ideas,
    _normalize_repo_assessment,
)
from backend.modules.trending_repos.idea_prompts import (
    FALLBACK_PRODUCT_HUNTER_PROMPT,
    build_ideas_prompt,
    _FALLBACK_PRODUCT_HUNTER_PROMPT,
    _build_ideas_prompt,
)
from backend.modules.trending_repos.models import TrendingRepo
from backend.modules.trending_repos.repository import TrendingReposRepository

logger = logging.getLogger(__name__)

MAX_README_PROMPT_CHARS = 6_000

__all__ = [
    "MAX_README_PROMPT_CHARS",
    "PLACEHOLDER_IDEA_VALUES",
    "ProductIdeasGenerator",
    "_FALLBACK_PRODUCT_HUNTER_PROMPT",
    "_build_ideas_prompt",
    "_format_product_hunter_result_preview",
    "_is_placeholder_idea",
    "_normalize_generated_ideas",
    "_normalize_repo_assessment",
]


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
        from backend.core.static_cache import load_text_file

        prompt_path = (
            Path(__file__).resolve().parents[2] / "prompts" / "product_hunter" / "v1" / "system.md"
        )
        if prompt_path.exists():
            return load_text_file(str(prompt_path))
        return FALLBACK_PRODUCT_HUNTER_PROMPT

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
            response = await request(
                "GET",
                f"{GITHUB_REPO_URL}/{full_name}/readme",
                provider="github",
                headers=self._build_github_headers("application/vnd.github.raw"),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning(
                "Failed to fetch README for repo %s; generating ideas without README", full_name
            )
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
        user_prompt = build_ideas_prompt(record, readme_excerpt=readme_excerpt)
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

        repo_assessment = normalize_repo_assessment(result.get("repo_assessment"))
        ideas = normalize_generated_ideas(result.get("ideas") or [])
        if not ideas:
            logger.warning(
                "Product hunter returned unusable structured output for repo %s (%s): %s",
                record.name,
                repo_id,
                format_product_hunter_result_preview(result),
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
