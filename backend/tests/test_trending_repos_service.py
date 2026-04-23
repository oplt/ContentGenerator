from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from backend.modules.inference.providers import ConfiguredLLMProvider, ProviderHealth
from backend.modules.trending_repos.service import (
    TrendingReposService,
    _build_ideas_prompt,
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
                "positioning": "string",
                "target_customer": "string",
                "pain_point": "string",
                "product_concept": "string",
            }
        ]
    )

    assert ideas == []


def test_normalize_generated_ideas_maps_product_hunter_schema() -> None:
    ideas = _normalize_generated_ideas(
        [
            {
                "title": "AgentOps Console",
                "pain_point": "Teams cannot observe agent failures.",
                "product_concept": "Hosted control plane for debugging and replay.",
                "target_customer": "AI product teams",
                "monetization": {
                    "model": "SaaS",
                    "pricing_logic": "$299/mo per workspace",
                    "estimated_willingness_to_pay": "High for production teams",
                },
                "positioning": "Replay any agent run in seconds.",
            }
        ]
    )

    assert ideas == [
        {
            "rank": 1,
            "title": "AgentOps Console",
            "positioning": "Replay any agent run in seconds.",
            "target_customer": "AI product teams",
            "pain_point": "Teams cannot observe agent failures.",
            "product_concept": "Hosted control plane for debugging and replay.",
            "why_this_repo_fits": "",
            "required_extensions": [],
            "monetization": {
                "model": "SaaS",
                "pricing_logic": "$299/mo per workspace",
                "estimated_willingness_to_pay": "High for production teams",
            },
            "scores": {
                "revenue_potential": 0,
                "customer_urgency": 0,
                "repo_leverage": 0,
                "speed_to_mvp": 0,
                "competitive_intensity": 0,
            },
            "time_to_mvp": "",
            "key_risks": [],
            "why_now": "",
            "investor_angle": "",
            "v1_scope": [],
            "not_for_v1": [],
        }
    ]


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
            "rank": 1,
            "title": "AgentOps Console",
            "positioning": "Replay any agent run in seconds.",
            "target_customer": "AI product teams",
            "pain_point": "Teams cannot observe agent failures.",
            "product_concept": "Hosted control plane for debugging and replay.",
            "why_this_repo_fits": "The repo already orchestrates long-running agents.",
            "required_extensions": ["Hosted auth and billing"],
            "monetization": {
                "model": "SaaS",
                "pricing_logic": "$299/mo per workspace",
                "estimated_willingness_to_pay": "High for production teams",
            },
            "scores": {
                "revenue_potential": 8,
                "customer_urgency": 8,
                "repo_leverage": 9,
                "speed_to_mvp": 7,
                "competitive_intensity": 6,
            },
            "time_to_mvp": "6 weeks",
            "key_risks": ["Crowded observability market"],
            "why_now": "Agent teams are moving into production.",
            "investor_angle": "Strong infra wedge with expansion revenue.",
            "v1_scope": ["Replay", "logs", "alerts"],
            "not_for_v1": ["Enterprise SSO"],
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
            ConfiguredLLMProvider,
            "generate_structured_json",
            new=AsyncMock(return_value={"ideas": ideas}),
        ) as mock_generate,
    ):
        updated = await svc.generate_product_ideas("tenant-1", "repo-1")

    prompt = mock_generate.await_args.args[0]
    assert "README excerpt:" in prompt
    assert "long-running agents" in prompt
    assert mock_generate.await_args.kwargs["task"] == "product_hunter"
    assert mock_generate.await_args.kwargs["max_tokens"] == 8192
    assert mock_generate.await_args.kwargs["temperature"] == 0.2
    assert updated.product_ideas == ideas
    assert updated.ideas_generated_at is not None


@pytest.mark.asyncio
async def test_generate_product_ideas_maps_product_hunter_schema_to_saved_ideas() -> None:
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
    svc._fetch_repo_readme_excerpt = AsyncMock(return_value=None)

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
            ConfiguredLLMProvider,
            "generate_structured_json",
            new=AsyncMock(
                return_value={
                    "ideas": [
                        {
                            "title": "AgentOps Console",
                            "pain_point": "Teams cannot observe agent failures.",
                            "product_concept": "Hosted control plane for debugging and replay.",
                            "target_customer": "AI product teams",
                            "monetization": {
                                "model": "SaaS",
                                "pricing_logic": "$299/mo per workspace",
                                "estimated_willingness_to_pay": "High for production teams",
                            },
                            "positioning": "Replay any agent run in seconds.",
                        }
                    ]
                }
            ),
        ),
    ):
        updated = await svc.generate_product_ideas("tenant-1", "repo-1")

    assert updated.product_ideas == [
        {
            "rank": 1,
            "title": "AgentOps Console",
            "positioning": "Replay any agent run in seconds.",
            "target_customer": "AI product teams",
            "pain_point": "Teams cannot observe agent failures.",
            "product_concept": "Hosted control plane for debugging and replay.",
            "why_this_repo_fits": "",
            "required_extensions": [],
            "monetization": {
                "model": "SaaS",
                "pricing_logic": "$299/mo per workspace",
                "estimated_willingness_to_pay": "High for production teams",
            },
            "scores": {
                "revenue_potential": 0,
                "customer_urgency": 0,
                "repo_leverage": 0,
                "speed_to_mvp": 0,
                "competitive_intensity": 0,
            },
            "time_to_mvp": "",
            "key_risks": [],
            "why_now": "",
            "investor_angle": "",
            "v1_scope": [],
            "not_for_v1": [],
        }
    ]
    svc.repo.save.assert_awaited_once_with(record)
    svc.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_product_ideas_fails_fast_when_configured_llm_is_unreachable() -> None:
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

    fake_settings = SimpleNamespace(
        LLM_PROVIDER="ollama",
        LLM_MODEL="llama3.1:latest",
        LLM_TIMEOUT_SECONDS=5.0,
        LLM_JSON_ENFORCEMENT="best_effort",
        llm_task_models={"product_hunter": "llama3.1:latest"},
        GITHUB_TOKEN="",
    )

    with (
        patch("backend.modules.trending_repos.service.settings", fake_settings),
        patch.object(
            TrendingReposService,
            "_get_llm_provider_health",
            new=AsyncMock(
                return_value=ProviderHealth(
                    provider_name="ollama",
                    status="error",
                    detail="[Errno 111] Connection refused",
                )
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="provider 'ollama' is unavailable"):
            await svc.generate_product_ideas("tenant-1", "repo-1")

    svc.repo.save.assert_not_awaited()
    svc.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_product_ideas_raises_when_llm_output_is_unusable() -> None:
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
    svc._fetch_repo_readme_excerpt = AsyncMock(return_value=None)

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
            TrendingReposService,
            "_get_llm_provider_health",
            new=AsyncMock(
                return_value=ProviderHealth(
                    provider_name="mock",
                    status="ok",
                    detail="mock provider",
                )
            ),
        ),
        patch.object(
            ConfiguredLLMProvider,
            "generate_structured_json",
            new=AsyncMock(return_value={"ideas": [{"title": "string"}]}),
        ),
    ):
        with pytest.raises(RuntimeError, match="No ideas were saved"):
            await svc.generate_product_ideas("tenant-1", "repo-1")

    svc.repo.save.assert_not_awaited()
    svc.db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_product_ideas_logs_unusable_llm_payload_preview(caplog) -> None:
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
    svc._fetch_repo_readme_excerpt = AsyncMock(return_value=None)

    fake_settings = SimpleNamespace(
        LLM_PROVIDER="mock",
        LLM_MODEL="gpt-4o-mini",
        LLM_TIMEOUT_SECONDS=5.0,
        LLM_JSON_ENFORCEMENT="best_effort",
        llm_task_models={"product_hunter": "gpt-4o-mini"},
        GITHUB_TOKEN="",
    )

    caplog.set_level(logging.WARNING)

    with (
        patch("backend.modules.trending_repos.service.settings", fake_settings),
        patch.object(
            TrendingReposService,
            "_get_llm_provider_health",
            new=AsyncMock(
                return_value=ProviderHealth(
                    provider_name="mock",
                    status="ok",
                    detail="mock provider",
                )
            ),
        ),
        patch.object(
            ConfiguredLLMProvider,
            "generate_structured_json",
            new=AsyncMock(
                return_value={
                    "repo_assessment": {"what_it_does": "scheduler"},
                    "ideas": [{"headline": "wrong key"}],
                }
            ),
        ),
    ):
        with pytest.raises(RuntimeError, match="No ideas were saved"):
            await svc.generate_product_ideas("tenant-1", "repo-1")

    assert "Product hunter returned unusable structured output" in caplog.text
    assert "first_idea_keys" in caplog.text
    assert "headline" in caplog.text


@pytest.mark.asyncio
async def test_send_daily_digest_to_telegram_uses_markdown_v2() -> None:
    svc = _svc()
    svc.db = AsyncMock()
    svc.repo = AsyncMock()

    tenant_id = uuid4()
    svc.repo.get_latest_by_period = AsyncMock(
        return_value=[
            SimpleNamespace(
                rank=1,
                name="acme/rocket",
                html_url="https://github.com/acme/rocket",
                stars_count=1234,
                language="TypeScript",
                description="Realtime agent runtime",
                product_ideas=[],
            )
        ]
    )

    mock_provider = AsyncMock()
    mock_provider.send_message = AsyncMock(return_value={"provider": "telegram", "message_id": "1"})

    with (
        patch(
            "backend.modules.settings.service.SettingsService.resolve_telegram_runtime_config",
            new=AsyncMock(return_value={"bot_token": "bot", "chat_id": "123", "enabled": True}),
        ),
        patch("backend.modules.approvals.providers.TelegramProvider", return_value=mock_provider),
    ):
        await svc.send_daily_digest_to_telegram(tenant_id)

    assert mock_provider.send_message.await_count == 1
    assert mock_provider.send_message.await_args.kwargs["parse_mode"] == "MarkdownV2"


@pytest.mark.asyncio
async def test_fetch_repo_readme_excerpt_returns_none_on_http_error() -> None:
    svc = _svc()
    transport = httpx.MockTransport(lambda request: httpx.Response(403, request=request))

    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)):
        excerpt = await svc._fetch_repo_readme_excerpt("acme/rocket")

    assert excerpt is None


@pytest.mark.asyncio
async def test_post_to_twitter_returns_actionable_message_on_x_403() -> None:
    svc = _svc()
    svc.db = AsyncMock()

    social_account = SimpleNamespace(
        id=uuid4(),
        handle="acme",
        account_metadata={"mode": "real"},
    )
    token_row = SimpleNamespace(access_token_encrypted="enc-token")

    request = httpx.Request("POST", "https://api.x.com/2/tweets")
    response = httpx.Response(
        403,
        request=request,
        json={"title": "Forbidden", "detail": "You are not permitted to perform this action."},
    )
    http_error = httpx.HTTPStatusError("403 Forbidden", request=request, response=response)

    with (
        patch(
            "backend.modules.publishing.repository.PublishingRepository.get_social_account_by_platform",
            new=AsyncMock(return_value=social_account),
        ),
        patch(
            "backend.modules.publishing.repository.PublishingRepository.get_token_for_account",
            new=AsyncMock(return_value=token_row),
        ),
        patch("backend.core.security.decrypt_secret", return_value="x-user-token"),
        patch("backend.modules.publishing.providers.XPublishingProvider._post_tweet", new=AsyncMock(side_effect=http_error)),
    ):
        with pytest.raises(ValueError) as exc_info:
            await svc.post_to_twitter(uuid4(), "Ship it")

    message = str(exc_info.value)
    assert "tweet.write" in message
    assert "Read and Write permissions" in message
    assert "App-only bearer tokens cannot post tweets" in message
