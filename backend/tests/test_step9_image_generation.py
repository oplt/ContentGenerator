"""
Tests for Step 9 — Image Generation.

Covers:
- ImageGenerationResult dataclass defaults
- MockImageProvider returns valid PNG bytes
- StableDiffusionProvider: success path, network failure fallback
- OpenAIImageProvider: success path, missing key fallback, network failure fallback
- get_image_provider factory dispatches correctly
- ImageGenerationService._build_prompt logic
- ImageGenerationService.generate_for_job: creates THUMBNAIL asset, stores to S3
- ImageGenerationService.generate_for_job: no bytes → returns None
- ImageGenerationService.generate_for_job: storage failure → asset created without URL
- ContentGenerationService.generate wires image generation and produces THUMBNAIL asset
"""
from __future__ import annotations

import base64
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.content_generation.image_providers import (
    ImageGenerationResult,
    MockImageProvider,
    OpenAIImageProvider,
    StableDiffusionProvider,
    _PLACEHOLDER_PNG,
    get_image_provider,
)
from backend.modules.content_generation.image_service import ImageGenerationService
from backend.modules.content_generation.models import GeneratedAsset, GeneratedAssetType


# ---------------------------------------------------------------------------
# ImageGenerationResult defaults
# ---------------------------------------------------------------------------

def test_image_generation_result_defaults() -> None:
    r = ImageGenerationResult()
    assert r.mime_type == "image/png"
    assert r.provider == "mock"
    assert r.image_bytes == b""
    assert r.width == 0
    assert r.height == 0


def test_placeholder_png_is_valid_bytes() -> None:
    # The placeholder must start with the PNG magic bytes
    assert _PLACEHOLDER_PNG[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# MockImageProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_provider_returns_png_bytes() -> None:
    provider = MockImageProvider()
    result = await provider.generate("test prompt")
    assert result.image_bytes == _PLACEHOLDER_PNG
    assert result.mime_type == "image/png"
    assert result.provider == "mock"
    assert result.prompt_used == "test prompt"


@pytest.mark.asyncio
async def test_mock_provider_non_empty_bytes() -> None:
    provider = MockImageProvider()
    result = await provider.generate("any")
    assert len(result.image_bytes) > 0


# ---------------------------------------------------------------------------
# StableDiffusionProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sd_provider_success_path() -> None:
    fake_png_b64 = base64.b64encode(_PLACEHOLDER_PNG).decode()
    fake_response = MagicMock()
    fake_response.json.return_value = {"images": [fake_png_b64]}
    fake_response.raise_for_status = MagicMock()

    with patch("backend.modules.content_generation.image_providers.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        provider = StableDiffusionProvider()
        result = await provider.generate("editorial photo of tech news")

    assert result.provider == "stable_diffusion"
    assert result.image_bytes == _PLACEHOLDER_PNG
    assert result.mime_type == "image/png"


@pytest.mark.asyncio
async def test_sd_provider_network_failure_returns_empty() -> None:
    with patch("backend.modules.content_generation.image_providers.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        provider = StableDiffusionProvider()
        result = await provider.generate("any prompt")

    assert result.provider == "stable_diffusion"
    assert result.image_bytes == b""  # empty — caller must handle


# ---------------------------------------------------------------------------
# OpenAIImageProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_provider_no_api_key_returns_empty() -> None:
    provider = OpenAIImageProvider()
    provider._api_key = ""
    result = await provider.generate("test")
    assert result.image_bytes == b""
    assert result.provider == "openai"


@pytest.mark.asyncio
async def test_openai_provider_success_path() -> None:
    fake_b64 = base64.b64encode(_PLACEHOLDER_PNG).decode()
    fake_response = MagicMock()
    fake_response.json.return_value = {"data": [{"b64_json": fake_b64}]}
    fake_response.raise_for_status = MagicMock()

    with patch("backend.modules.content_generation.image_providers.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        provider = OpenAIImageProvider()
        provider._api_key = "sk-test"
        result = await provider.generate("news photo")

    assert result.provider == "openai"
    assert result.image_bytes == _PLACEHOLDER_PNG


@pytest.mark.asyncio
async def test_openai_provider_http_error_returns_empty() -> None:
    with patch("backend.modules.content_generation.image_providers.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("500 server error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        provider = OpenAIImageProvider()
        provider._api_key = "sk-test"
        result = await provider.generate("test")

    assert result.image_bytes == b""


# ---------------------------------------------------------------------------
# get_image_provider factory
# ---------------------------------------------------------------------------

def test_factory_returns_mock_by_default() -> None:
    provider = get_image_provider("mock")
    assert isinstance(provider, MockImageProvider)


def test_factory_returns_sd_provider() -> None:
    provider = get_image_provider("stable_diffusion")
    assert isinstance(provider, StableDiffusionProvider)


def test_factory_returns_openai_provider() -> None:
    provider = get_image_provider("openai")
    assert isinstance(provider, OpenAIImageProvider)


def test_factory_unknown_defaults_to_mock() -> None:
    provider = get_image_provider("nonexistent")
    assert isinstance(provider, MockImageProvider)


# ---------------------------------------------------------------------------
# ImageGenerationService._build_prompt
# ---------------------------------------------------------------------------

def test_build_prompt_includes_topic_and_keywords() -> None:
    svc = object.__new__(ImageGenerationService)
    prompt = svc._build_prompt("Headline", "technology", "AI, chips, GPU")
    assert "technology" in prompt
    assert "AI, chips, GPU" in prompt
    assert "editorial photography" in prompt


def test_build_prompt_truncated_to_400_chars() -> None:
    svc = object.__new__(ImageGenerationService)
    long_keywords = "keyword " * 100
    prompt = svc._build_prompt("H", "topic", long_keywords)
    assert len(prompt) <= 400


def test_build_prompt_no_keywords_still_valid() -> None:
    svc = object.__new__(ImageGenerationService)
    prompt = svc._build_prompt("Breaking news", "politics", "")
    assert "politics" in prompt
    assert len(prompt) > 0


# ---------------------------------------------------------------------------
# ImageGenerationService.generate_for_job
# ---------------------------------------------------------------------------

def _make_img_service(provider=None) -> ImageGenerationService:
    svc = object.__new__(ImageGenerationService)
    svc.db = AsyncMock()
    svc.provider = provider or MockImageProvider()
    return svc


@pytest.mark.asyncio
async def test_generate_for_job_creates_thumbnail_asset() -> None:
    svc = _make_img_service()
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch("backend.modules.content_generation.image_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = AsyncMock(return_value="http://localhost:9000/bucket/key.png")

        asset = await svc.generate_for_job(
            tenant_id=tenant_id,
            job_id=job_id,
            headline="Test headline",
            primary_topic="technology",
            keywords="AI, chips",
            platform="x",
        )

    assert asset is not None
    assert asset.asset_type == GeneratedAssetType.THUMBNAIL.value
    assert asset.platform == "x"
    assert asset.variant_label == "cover"
    assert asset.public_url == "http://localhost:9000/bucket/key.png"
    assert asset.mime_type == "image/png"
    assert asset.size_bytes > 0
    assert asset.checksum is not None
    assert asset.asset_metadata["image_provider"] == "mock"
    svc.db.add.assert_called_once()
    svc.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_for_job_returns_none_when_no_bytes() -> None:
    empty_provider = MagicMock(spec=MockImageProvider)
    empty_provider.generate = AsyncMock(return_value=ImageGenerationResult(image_bytes=b"", provider="mock"))
    svc = _make_img_service(provider=empty_provider)

    result = await svc.generate_for_job(
        tenant_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        headline="Test",
        primary_topic="test",
    )

    assert result is None
    svc.db.add.assert_not_called()


@pytest.mark.asyncio
async def test_generate_for_job_storage_failure_creates_asset_without_url() -> None:
    svc = _make_img_service()
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch("backend.modules.content_generation.image_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = AsyncMock(side_effect=Exception("MinIO down"))

        asset = await svc.generate_for_job(
            tenant_id=tenant_id,
            job_id=job_id,
            headline="Test",
            primary_topic="test",
        )

    assert asset is not None
    assert asset.public_url is None
    assert asset.storage_key is None
    assert asset.size_bytes > 0  # bytes were still generated


@pytest.mark.asyncio
async def test_generate_for_job_storage_not_configured_skips_upload() -> None:
    svc = _make_img_service()

    with patch("backend.modules.content_generation.image_service.object_storage") as mock_storage:
        mock_storage.is_configured = False

        asset = await svc.generate_for_job(
            tenant_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            headline="Test",
            primary_topic="test",
        )

    assert asset is not None
    assert asset.public_url is None


@pytest.mark.asyncio
async def test_generate_for_job_storage_key_includes_tenant_and_job() -> None:
    svc = _make_img_service()
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    captured_key: list[str] = []

    async def capture_upload(*, object_key, body, content_type):
        captured_key.append(object_key)
        return f"http://storage/{object_key}"

    with patch("backend.modules.content_generation.image_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = capture_upload

        await svc.generate_for_job(
            tenant_id=tenant_id,
            job_id=job_id,
            headline="Test",
            primary_topic="test",
            platform="instagram",
        )

    assert len(captured_key) == 1
    key = captured_key[0]
    assert str(tenant_id) in key
    assert str(job_id) in key
    assert "instagram" in key


# ---------------------------------------------------------------------------
# Integration: ContentGenerationService.generate produces THUMBNAIL asset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_pipeline_produces_thumbnail_asset() -> None:
    """generate() must call ImageGenerationService and create a THUMBNAIL asset."""
    from backend.modules.content_generation.service import ContentGenerationService
    from backend.modules.editorial_briefs.models import BriefStatus

    svc = object.__new__(ContentGenerationService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.plan_repo = AsyncMock()
    svc.story_repo = AsyncMock()
    svc.audit = AsyncMock()
    svc.video_pipeline = AsyncMock()
    svc.llm = AsyncMock()

    tenant_id = uuid.uuid4()

    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.story_cluster_id = uuid.uuid4()
    plan.decision = "generate"
    plan.content_format = "text"
    plan.tone = "authoritative"
    plan.target_platforms = ["x"]
    plan.hashtags_strategy = "balanced"
    plan.recommended_cta = ""
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = uuid.uuid4()
    cluster.headline = "Test headline"
    cluster.summary = "Summary"
    cluster.primary_topic = "technology"
    cluster.explainability = {"keywords": "AI, chips"}
    cluster.content_vertical = "technology"
    cluster.risk_level = "safe"
    svc.story_repo.get_cluster = AsyncMock(return_value=cluster)
    svc.story_repo.list_normalized_for_cluster = AsyncMock(return_value=[])

    brief = MagicMock()
    brief.status = BriefStatus.APPROVED.value
    brief.angle = ""
    brief.talking_points = []

    job = MagicMock()
    job.id = uuid.uuid4()
    job.grounding_bundle = {"headline": "Test headline", "summary": "Summary", "topic": "technology"}
    svc.repo.create_job = AsyncMock(return_value=job)

    orch_result = MagicMock()
    orch_result.reviewer.passed = True
    orch_result.scorer.composite = 0.7
    orch_result.scorer.reasoning = "Good"
    orch_result.reviewer.issues = []
    orch_result.extractor.content_vertical = "technology"
    orch_result.extractor.risk_flags = []
    orch_result.planner.target_platforms = ["x"]
    orch_result.planner.recommended_format = "text"
    orch_result.writer.drafts = {"x": "Draft text"}
    orch_result.optimizer.variants = []
    orch_result.optimizer.recommended_variant_index = 0
    orch_result.final_draft = "Draft text"

    img_generate_calls: list[dict] = []

    mock_img_asset = MagicMock(spec=GeneratedAsset)
    mock_img_asset.asset_type = GeneratedAssetType.THUMBNAIL.value

    async def fake_generate_for_job(**kwargs):
        img_generate_calls.append(kwargs)
        return mock_img_asset

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as mock_brief_cls,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as mock_orch_cls,
        patch("backend.modules.content_generation.image_service.ImageGenerationService") as mock_img_cls,
    ):
        mock_brief_cls.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_orch = AsyncMock()
        mock_orch.run = AsyncMock(return_value=orch_result)
        mock_orch_cls.return_value = mock_orch

        mock_img_instance = AsyncMock()
        mock_img_instance.generate_for_job = AsyncMock(side_effect=fake_generate_for_job)
        mock_img_cls.return_value = mock_img_instance

        await svc.generate(tenant_id=tenant_id, plan_id=plan.id)

    assert len(img_generate_calls) == 1
    call = img_generate_calls[0]
    assert call["tenant_id"] == tenant_id
    assert call["job_id"] == job.id
    assert call["platform"] == "x"
    assert call["primary_topic"] == "technology"
