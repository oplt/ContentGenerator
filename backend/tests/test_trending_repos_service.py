from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.modules.inference.providers import RoutedLLMProvider
from backend.modules.trending_repos.service import (
    TrendingReposService,
    _build_ideas_prompt,
    _build_fallback_ideas,
    _normalize_generated_ideas,
    _parse_count,
)


TRENDING_HTML = """
<article class="Box-row">
  <h2>
    <a href="/acme/rocket"> acme / rocket </a>
  </h2>
  <p>Realtime agent runtime.</p>
  <div>
    <span itemprop="programmingLanguage">TypeScript</span>
    <a href="/acme/rocket/stargazers">1,234</a>
    <a href="/acme/rocket/forks">56</a>
    <span>321 stars today</span>
  </div>
</article>
<article class="Box-row">
  <h2>
    <a href="/orbital/drive"> orbital / drive </a>
  </h2>
  <div>
    <a href="/orbital/drive/stargazers">2.5k</a>
    <a href="/orbital/drive/forks">120</a>
    <span>1.2k stars today</span>
  </div>
</article>
"""


def _svc() -> TrendingReposService:
    return object.__new__(TrendingReposService)


@pytest.mark.asyncio
async def test_parse_trending_html_extracts_repo_order_and_stats() -> None:
    svc = _svc()

    repos = svc._parse_trending_html(TRENDING_HTML)

    assert [repo["full_name"] for repo in repos] == ["acme/rocket", "orbital/drive"]
    assert repos[0]["description"] == "Realtime agent runtime."
    assert repos[0]["language"] == "TypeScript"
    assert repos[0]["stars_count"] == 1234
    assert repos[0]["forks_count"] == 56
    assert repos[0]["stars_gained"] == 321
    assert repos[1]["stars_count"] == 2500
    assert repos[1]["stars_gained"] == 1200


@pytest.mark.asyncio
async def test_fetch_from_github_falls_back_to_search_proxy_when_trending_fails() -> None:
    svc = _svc()
    fallback = [
        {
            "github_id": 1,
            "name": "fallback/repo",
            "full_name": "fallback/repo",
            "description": "fallback",
            "html_url": "https://github.com/fallback/repo",
            "language": "Python",
            "topics": [],
            "stars_count": 999,
            "forks_count": 12,
            "watchers_count": 999,
            "open_issues_count": 3,
            "stars_gained": 999,
        }
    ]

    with (
        patch.object(
            TrendingReposService,
            "_fetch_from_github_trending",
            new=AsyncMock(side_effect=httpx.HTTPError("boom")),
        ),
        patch.object(
            TrendingReposService,
            "_fetch_from_github_search",
            new=AsyncMock(return_value=fallback),
        ),
    ):
        repos = await svc.fetch_from_github("daily")

    assert repos == fallback


def test_parse_count_supports_compact_suffixes() -> None:
    assert _parse_count("1,234") == 1234
    assert _parse_count("2.5k") == 2500
    assert _parse_count("3m") == 3_000_000


def test_build_ideas_prompt_includes_repo_content_context() -> None:
    record = SimpleNamespace(
        full_name="acme/rocket",
        description="Realtime agent runtime",
        language="TypeScript",
        topics=["agents", "runtime"],
        stars_count=1234,
        stars_gained=321,
        html_url="https://github.com/acme/rocket",
    )

    prompt = _build_ideas_prompt(
        record, readme_excerpt="This repo orchestrates long-running agents."
    )

    assert "README excerpt:" in prompt
    assert "most valuable" in prompt
    assert "long-running agents" in prompt


def test_normalize_generated_ideas_filters_schema_placeholders() -> None:
    ideas = _normalize_generated_ideas(
        [
            {
                "title": "string",
                "problem": "string",
                "solution": "string",
                "target_audience": "string",
                "monetization": "string",
                "wow_factor": "string",
            }
        ]
    )

    assert ideas == []


def test_build_fallback_ideas_creates_non_placeholder_content() -> None:
    record = SimpleNamespace(
        full_name="acme/rocket",
        description="Realtime agent runtime",
        language="TypeScript",
        topics=["agents", "runtime"],
    )

    ideas = _build_fallback_ideas(record)

    assert len(ideas) == 5
    assert all(idea["title"] != "string" for idea in ideas)
    assert any("acme/rocket" in idea["solution"] for idea in ideas)


@pytest.mark.asyncio
async def test_generate_product_ideas_requires_llm_provider() -> None:
    svc = _svc()

    with patch(
        "backend.modules.trending_repos.service.settings",
        SimpleNamespace(LLM_PROVIDER=""),
    ):
        with pytest.raises(RuntimeError, match="local LLM model"):
            svc._get_product_ideas_llm()


@pytest.mark.asyncio
async def test_generate_product_ideas_uses_router_with_repo_readme() -> None:
    svc = _svc()
    svc.db = AsyncMock()
    svc.repo = AsyncMock()

    record = SimpleNamespace(
        id="repo-1",
        name="acme/rocket",
        full_name="acme/rocket",
        description="Realtime agent runtime",
        language="TypeScript",
        topics=["agents", "runtime"],
        stars_count=1234,
        stars_gained=321,
        html_url="https://github.com/acme/rocket",
        product_ideas=[],
        ideas_generated_at=None,
    )
    svc.repo.get_by_id = AsyncMock(return_value=record)
    svc.repo.save = AsyncMock(return_value=record)
    svc._fetch_repo_readme_excerpt = AsyncMock(
        return_value="This repo orchestrates long-running agents."
    )

    ideas = [
        {
            "title": "AgentOps Console",
            "problem": "Teams cannot observe agent failures.",
            "solution": "Hosted control plane for debugging and replay.",
            "target_audience": "AI product teams",
            "monetization": "$299/mo per workspace",
            "wow_factor": "Replay any agent run in seconds.",
        }
    ]

    fake_settings = SimpleNamespace(
        LLM_PROVIDER="mock",
        LLM_MODEL="gpt-4o-mini",
        LLM_TIMEOUT_SECONDS=5.0,
        LLM_JSON_ENFORCEMENT="best_effort",
        llm_task_models={"product_hunter": "gpt-4o-mini"},
        GITHUB_TOKEN="",
    )

    with (
        patch("backend.modules.trending_repos.service.settings", fake_settings),
        patch.object(
            RoutedLLMProvider,
            "generate_structured_json",
            new=AsyncMock(return_value={"ideas": ideas}),
        ) as mock_generate,
    ):
        updated = await svc.generate_product_ideas("tenant-1", "repo-1")

    prompt = mock_generate.await_args.args[0]
    assert "README excerpt:" in prompt
    assert "long-running agents" in prompt
    assert mock_generate.await_args.kwargs["task"] == "product_hunter"
    assert updated.product_ideas == ideas
    assert updated.ideas_generated_at is not None


@pytest.mark.asyncio
async def test_fetch_repo_readme_excerpt_returns_none_on_http_error() -> None:
    svc = _svc()
    transport = httpx.MockTransport(lambda request: httpx.Response(403, request=request))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        excerpt = await svc._fetch_repo_readme_excerpt("acme/rocket")

    assert excerpt is None
