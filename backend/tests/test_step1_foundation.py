"""
Tests for Step 1 — Foundation Hardening.

Covers:
- Real embedding provider selection (OllamaEmbeddingsProvider / HashingEmbeddingsProvider)
- Embedding stored as list[float], not list[str]
- Story clustering uses float embeddings correctly
- cosine_similarity function
- PublishingJobStatus includes CLAIMED, DEAD, SUCCEEDED_DRY_RUN
- claim_due_jobs returns no duplicates (idempotency / race-condition safety)
- celery_app beat schedule includes rescore_all_tenants_task
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.story_intelligence.providers import (
    HashingEmbeddingsProvider,
    LlamaCppProvider,
    OllamaEmbeddingsProvider,
    RoutedLLMProvider,
    VLLMProvider,
    cosine_similarity,
    get_embeddings_provider,
    get_llm_provider,
)
from backend.modules.publishing.models import PublishingJobStatus


# ---------------------------------------------------------------------------
# cosine_similarity unit tests
# ---------------------------------------------------------------------------

def test_cosine_similarity_identical() -> None:
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_empty_left() -> None:
    assert cosine_similarity([], [1.0, 0.0]) == 0.0


def test_cosine_similarity_dimension_mismatch() -> None:
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_zero_vector() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


# ---------------------------------------------------------------------------
# HashingEmbeddingsProvider (always available, no network)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hashing_embeddings_returns_floats() -> None:
    provider = HashingEmbeddingsProvider(dimensions=24)
    embedding = await provider.embed("Federal Reserve raises interest rates")
    assert isinstance(embedding, list)
    assert all(isinstance(v, float) for v in embedding)
    assert len(embedding) == 24


@pytest.mark.asyncio
async def test_hashing_embeddings_normalised() -> None:
    provider = HashingEmbeddingsProvider(dimensions=24)
    embedding = await provider.embed("Some article text")
    norm = math.sqrt(sum(v * v for v in embedding))
    assert norm == pytest.approx(1.0, abs=1e-6)


@pytest.mark.asyncio
async def test_hashing_embeddings_empty_text() -> None:
    provider = HashingEmbeddingsProvider(dimensions=24)
    embedding = await provider.embed("")
    assert all(v == 0.0 for v in embedding)


@pytest.mark.asyncio
async def test_hashing_embeddings_different_texts() -> None:
    provider = HashingEmbeddingsProvider(dimensions=24)
    e1 = await provider.embed("Central bank policy")
    e2 = await provider.embed("Football match results")
    # Should not be identical
    assert e1 != e2


# ---------------------------------------------------------------------------
# OllamaEmbeddingsProvider (mocked — no real Ollama needed in unit tests)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_embeddings_provider_calls_correct_endpoint() -> None:
    """OllamaEmbeddingsProvider should POST to /api/embeddings and return floats."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3, 0.4]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = OllamaEmbeddingsProvider(
            model="nomic-embed-text", base_url="http://localhost:11434"
        )
        embedding = await provider.embed("Test article")

    assert embedding == [0.1, 0.2, 0.3, 0.4]
    call_kwargs = mock_client.post.call_args
    assert "/api/embeddings" in call_kwargs[0][0]
    assert call_kwargs[1]["json"]["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_ollama_embeddings_provider_raises_on_empty_vector() -> None:
    """OllamaEmbeddingsProvider raises ValueError if Ollama returns empty embedding."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": []}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = OllamaEmbeddingsProvider(model="nomic-embed-text")
        with pytest.raises(ValueError, match="empty vector"):
            await provider.embed("Test")


# ---------------------------------------------------------------------------
# get_embeddings_provider factory
# ---------------------------------------------------------------------------

def test_get_embeddings_provider_returns_ollama_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.modules.story_intelligence.providers.settings",
        MagicMock(
            EMBEDDINGS_PROVIDER="ollama",
            EMBEDDINGS_MODEL="nomic-embed-text",
            OLLAMA_BASE_URL="http://localhost:11434",
            APP_ENV="development",
        ),
    )
    from backend.modules.story_intelligence.providers import get_embeddings_provider as gep
    provider = gep()
    assert isinstance(provider, OllamaEmbeddingsProvider)


def test_get_embeddings_provider_returns_hashing_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.modules.story_intelligence.providers.settings",
        MagicMock(
            EMBEDDINGS_PROVIDER="hashing",
            EMBEDDINGS_MODEL="hashing-v1",
            OLLAMA_BASE_URL="http://localhost:11434",
            APP_ENV="development",
        ),
    )
    from backend.modules.story_intelligence.providers import get_embeddings_provider as gep
    provider = gep()
    assert isinstance(provider, HashingEmbeddingsProvider)


def test_get_embeddings_provider_raises_hashing_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.modules.story_intelligence.providers.settings",
        MagicMock(
            EMBEDDINGS_PROVIDER="hashing",
            EMBEDDINGS_MODEL="hashing-v1",
            OLLAMA_BASE_URL="http://localhost:11434",
            APP_ENV="production",
        ),
    )
    from backend.modules.story_intelligence.providers import get_embeddings_provider as gep
    with pytest.raises(RuntimeError, match="not supported in production"):
        gep()


def test_get_llm_provider_returns_router_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.modules.story_intelligence.providers.settings",
        MagicMock(
            LLM_PROVIDER="vllm",
            VLLM_BASE_URL="http://localhost:8001/v1",
            LLAMACPP_BASE_URL="http://localhost:8080/v1",
            LLM_BASE_URL="",
            LLM_API_KEY="",
            LLM_MODEL="model",
            LLM_MAX_RETRIES=0,
            LLM_TASK_PROVIDER_OVERRIDES_JSON="{}",
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_fallback_order=["llamacpp", "mock"],
            llm_task_models={},
            LLM_TIMEOUT_SECONDS=30.0,
            LLM_JSON_ENFORCEMENT="best_effort",
        ),
    )
    provider = get_llm_provider()
    assert isinstance(provider, RoutedLLMProvider)


def test_get_llm_provider_returns_named_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.modules.story_intelligence.providers.settings",
        MagicMock(
            LLM_PROVIDER="llamacpp",
            VLLM_BASE_URL="http://localhost:8001/v1",
            LLAMACPP_BASE_URL="http://localhost:8080/v1",
            LLM_BASE_URL="",
            LLM_API_KEY="",
            LLM_MODEL="model",
            LLM_MAX_RETRIES=0,
            LLM_TASK_PROVIDER_OVERRIDES_JSON="{}",
            LLM_TASK_REQUIREMENTS_JSON="{}",
            LLM_PROVIDER_CAPABILITIES_JSON="{}",
            llm_fallback_order=["vllm", "mock"],
            llm_task_models={},
            LLM_TIMEOUT_SECONDS=30.0,
            LLM_JSON_ENFORCEMENT="best_effort",
        ),
    )
    provider = get_llm_provider("llamacpp")
    assert isinstance(provider, LlamaCppProvider)

    provider = get_llm_provider("vllm")
    assert isinstance(provider, VLLMProvider)


# ---------------------------------------------------------------------------
# NormalizedArticle.embedding is list[float] (not list[str])
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalized_article_embedding_is_float_list(
    db_session,
    seeded_context,
) -> None:
    """
    After normalization, embedding field must contain floats, not strings.
    """
    from backend.modules.source_ingestion.models import RawArticle, Source, SourceType
    from backend.modules.story_intelligence.service import StoryIntelligenceService

    tenant_id = seeded_context["tenant"].id
    source = Source(
        tenant_id=tenant_id,
        name="Test Feed",
        source_type=SourceType.RSS,
        url="http://example.com/feed",
        trust_score=0.8,
    )
    db_session.add(source)
    await db_session.flush()

    raw_article = RawArticle(
        tenant_id=tenant_id,
        source_id=source.id,
        url="http://example.com/article/1",
        canonical_url="http://example.com/article/1",
        content_hash="abc123" + str(uuid.uuid4()),
        title="Federal Reserve signals rate pause",
        summary="Fed signals pause in rate hikes.",
        body="The Federal Reserve today signaled a pause in its rate hiking cycle.",
    )
    db_session.add(raw_article)
    await db_session.flush()

    service = StoryIntelligenceService(db_session)
    normalized = await service.normalize_article(raw_article, source)

    assert isinstance(normalized.embedding, list), "embedding should be a list"
    assert len(normalized.embedding) > 0, "embedding should not be empty"
    for val in normalized.embedding:
        assert isinstance(val, float), f"embedding values must be float, got {type(val)}: {val!r}"


# ---------------------------------------------------------------------------
# PublishingJobStatus includes new statuses
# ---------------------------------------------------------------------------

def test_publishing_job_status_has_claimed() -> None:
    assert PublishingJobStatus.CLAIMED == "claimed"


def test_publishing_job_status_has_dead() -> None:
    assert PublishingJobStatus.DEAD == "dead"


def test_publishing_job_status_has_succeeded_dry_run() -> None:
    assert PublishingJobStatus.SUCCEEDED_DRY_RUN == "succeeded_dry_run"


# ---------------------------------------------------------------------------
# claim_due_jobs — idempotency / no double-claim
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claim_due_jobs_marks_claimed(db_session, seeded_context) -> None:
    """
    Jobs that become due should be claimed and status set to CLAIMED.

    NOTE: FOR UPDATE SKIP LOCKED is a PostgreSQL feature. The SQLite in-memory
    test DB verifies the status transition logic only. Real race-condition safety
    is enforced at the PostgreSQL level in production.
    """
    from backend.modules.publishing.models import PublishingJob, SocialPlatform
    from backend.modules.publishing.repository import PublishingRepository

    tenant_id = seeded_context["tenant"].id

    # Use raw INSERT-like approach: create job directly without FK constraint
    # by bypassing normal ORM init — instead just check behavior with a job
    # that has a dummy content_job_id (UUID only; FK not enforced in SQLite).
    fake_content_job_id = uuid.uuid4()

    now = datetime.now(timezone.utc)
    job = PublishingJob(
        tenant_id=tenant_id,
        content_job_id=fake_content_job_id,
        platform=SocialPlatform.X.value,
        status="pending",
        idempotency_key=str(uuid.uuid4()),
        dry_run=True,
        scheduled_for=now - timedelta(minutes=1),
    )
    db_session.add(job)
    await db_session.flush()

    repo = PublishingRepository(db_session)
    claimed = await repo.claim_due_jobs(worker_id="test-worker-1")

    assert len(claimed) == 1
    assert claimed[0].status == "claimed"
    assert claimed[0].worker_id == "test-worker-1"
    assert claimed[0].claimed_at is not None

    # Calling again should return nothing (already claimed — claimed_at IS NOT NULL)
    claimed_again = await repo.claim_due_jobs(worker_id="test-worker-2")
    assert len(claimed_again) == 0


# ---------------------------------------------------------------------------
# Beat schedule includes rescore_all_tenants_task
# ---------------------------------------------------------------------------

def test_beat_schedule_includes_rescore_all_tenants() -> None:
    from backend.workers.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    task_names = [entry["task"] for entry in schedule.values()]
    assert "backend.workers.tasks.rescore_all_tenants_task" in task_names


def test_beat_schedule_includes_publish_due_jobs() -> None:
    from backend.workers.celery_app import celery_app
    schedule = celery_app.conf.beat_schedule
    task_names = [entry["task"] for entry in schedule.values()]
    assert "backend.workers.tasks.publish_due_jobs_task" in task_names
