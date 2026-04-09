"""
Tests for Step 10 — Text-to-Speech (TTS).

Covers:
- _silent_wav produces a valid WAV binary
- TTSResult dataclass defaults
- MockTTSProvider returns non-empty WAV bytes
- PiperTTSProvider: missing model falls back to silence
- PiperTTSProvider: subprocess success path
- PiperTTSProvider: subprocess failure falls back to silence
- KokoroTTSProvider: HTTP success path
- KokoroTTSProvider: HTTP failure falls back to silence
- OpenAITTSProvider: missing API key falls back to silence
- OpenAITTSProvider: HTTP success path (MP3)
- OpenAITTSProvider: HTTP failure falls back to silence
- ElevenLabsTTSProvider: missing API key falls back to silence
- ElevenLabsTTSProvider: HTTP success path
- ElevenLabsTTSProvider: HTTP failure falls back to silence
- get_tts_provider factory dispatches correctly
- TTSService._build_script includes headline, summary, cta
- TTSService.generate_for_job: creates VOICEOVER asset + uploads to storage
- TTSService.generate_for_job: empty bytes → returns None
- TTSService.generate_for_job: storage failure → asset without URL
- TTSService.generate_for_job: storage not configured → asset without URL
- TTSService.generate_for_job: storage key includes tenant + job + platform
- ContentGenerationService.generate wires TTS and produces VOICEOVER asset
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.content_generation.tts_providers import (
    ElevenLabsTTSProvider,
    KokoroTTSProvider,
    MockTTSProvider,
    OpenAITTSProvider,
    PiperTTSProvider,
    TTSResult,
    _silent_wav,
    get_tts_provider,
)
from backend.modules.content_generation.tts_service import TTSService
from backend.modules.content_generation.models import GeneratedAsset, GeneratedAssetType


# ---------------------------------------------------------------------------
# _silent_wav helper
# ---------------------------------------------------------------------------

def test_silent_wav_starts_with_riff_header() -> None:
    wav = _silent_wav()
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"


def test_silent_wav_non_empty() -> None:
    assert len(_silent_wav()) > 100


def test_silent_wav_duration_affects_size() -> None:
    wav1 = _silent_wav(duration_seconds=1)
    wav3 = _silent_wav(duration_seconds=3)
    assert len(wav3) > len(wav1)


# ---------------------------------------------------------------------------
# TTSResult defaults
# ---------------------------------------------------------------------------

def test_tts_result_defaults() -> None:
    r = TTSResult()
    assert r.audio_bytes == b""
    assert r.mime_type == "audio/wav"
    assert r.provider == "mock"
    assert r.script_used == ""


# ---------------------------------------------------------------------------
# MockTTSProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_provider_returns_wav_bytes() -> None:
    provider = MockTTSProvider()
    result = await provider.synthesize("Hello world")
    assert result.audio_bytes[:4] == b"RIFF"
    assert result.mime_type == "audio/wav"
    assert result.provider == "mock"
    assert result.script_used == "Hello world"


@pytest.mark.asyncio
async def test_mock_provider_non_empty() -> None:
    provider = MockTTSProvider()
    result = await provider.synthesize("test")
    assert len(result.audio_bytes) > 0


# ---------------------------------------------------------------------------
# PiperTTSProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_piper_no_model_falls_back_to_silence() -> None:
    provider = PiperTTSProvider()
    provider._model = ""
    result = await provider.synthesize("test")
    assert result.provider == "piper"
    assert result.audio_bytes[:4] == b"RIFF"


@pytest.mark.asyncio
async def test_piper_subprocess_success() -> None:
    fake_wav = _silent_wav()

    async def fake_to_thread(fn):
        return fake_wav

    provider = PiperTTSProvider()
    provider._model = "/fake/model.onnx"

    with patch("backend.modules.content_generation.tts_providers.asyncio.to_thread",
               side_effect=fake_to_thread):
        result = await provider.synthesize("test script")

    assert result.provider == "piper"
    assert result.audio_bytes == fake_wav
    assert result.mime_type == "audio/wav"


@pytest.mark.asyncio
async def test_piper_subprocess_failure_falls_back() -> None:
    async def raise_error(fn):
        raise FileNotFoundError("piper not found")

    provider = PiperTTSProvider()
    provider._model = "/fake/model.onnx"

    with patch("backend.modules.content_generation.tts_providers.asyncio.to_thread",
               side_effect=raise_error):
        result = await provider.synthesize("test")

    assert result.provider == "piper"
    assert result.audio_bytes[:4] == b"RIFF"  # fallback silence


# ---------------------------------------------------------------------------
# KokoroTTSProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kokoro_success_path() -> None:
    fake_wav = _silent_wav()
    fake_response = MagicMock()
    fake_response.content = fake_wav
    fake_response.raise_for_status = MagicMock()

    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = KokoroTTSProvider()
        result = await provider.synthesize("Test news update.")

    assert result.provider == "kokoro"
    assert result.audio_bytes == fake_wav
    assert result.mime_type == "audio/wav"


@pytest.mark.asyncio
async def test_kokoro_failure_falls_back_to_silence() -> None:
    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = KokoroTTSProvider()
        result = await provider.synthesize("test")

    assert result.provider == "kokoro"
    assert result.audio_bytes[:4] == b"RIFF"


# ---------------------------------------------------------------------------
# OpenAITTSProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_tts_no_key_falls_back() -> None:
    provider = OpenAITTSProvider()
    provider._api_key = ""
    result = await provider.synthesize("test")
    assert result.provider == "openai"
    assert result.audio_bytes[:4] == b"RIFF"  # fallback WAV


@pytest.mark.asyncio
async def test_openai_tts_success_path() -> None:
    fake_mp3 = b"ID3" + b"\x00" * 100  # fake MP3 header
    fake_response = MagicMock()
    fake_response.content = fake_mp3
    fake_response.raise_for_status = MagicMock()

    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = OpenAITTSProvider()
        provider._api_key = "sk-test"
        result = await provider.synthesize("Test script")

    assert result.provider == "openai"
    assert result.mime_type == "audio/mpeg"
    assert result.audio_bytes == fake_mp3


@pytest.mark.asyncio
async def test_openai_tts_http_error_falls_back() -> None:
    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("503"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = OpenAITTSProvider()
        provider._api_key = "sk-test"
        result = await provider.synthesize("test")

    assert result.audio_bytes[:4] == b"RIFF"


# ---------------------------------------------------------------------------
# ElevenLabsTTSProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_elevenlabs_no_key_falls_back() -> None:
    provider = ElevenLabsTTSProvider()
    provider._api_key = ""
    result = await provider.synthesize("test")
    assert result.provider == "elevenlabs"
    assert result.audio_bytes[:4] == b"RIFF"


@pytest.mark.asyncio
async def test_elevenlabs_success_path() -> None:
    fake_mp3 = b"ID3" + b"\x00" * 100
    fake_response = MagicMock()
    fake_response.content = fake_mp3
    fake_response.raise_for_status = MagicMock()

    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fake_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = ElevenLabsTTSProvider()
        provider._api_key = "el-test"
        result = await provider.synthesize("test")

    assert result.provider == "elevenlabs"
    assert result.mime_type == "audio/mpeg"
    assert result.audio_bytes == fake_mp3


@pytest.mark.asyncio
async def test_elevenlabs_http_error_falls_back() -> None:
    with patch("backend.modules.content_generation.tts_providers.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("429 rate limit"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        provider = ElevenLabsTTSProvider()
        provider._api_key = "el-test"
        result = await provider.synthesize("test")

    assert result.audio_bytes[:4] == b"RIFF"


# ---------------------------------------------------------------------------
# get_tts_provider factory
# ---------------------------------------------------------------------------

def test_factory_mock() -> None:
    assert isinstance(get_tts_provider("mock"), MockTTSProvider)


def test_factory_piper() -> None:
    assert isinstance(get_tts_provider("piper"), PiperTTSProvider)


def test_factory_kokoro() -> None:
    assert isinstance(get_tts_provider("kokoro"), KokoroTTSProvider)


def test_factory_openai() -> None:
    assert isinstance(get_tts_provider("openai"), OpenAITTSProvider)


def test_factory_elevenlabs() -> None:
    assert isinstance(get_tts_provider("elevenlabs"), ElevenLabsTTSProvider)


def test_factory_unknown_defaults_to_mock() -> None:
    assert isinstance(get_tts_provider("unknown_engine"), MockTTSProvider)


# ---------------------------------------------------------------------------
# TTSService._build_script
# ---------------------------------------------------------------------------

def test_build_script_includes_headline_and_summary() -> None:
    svc = object.__new__(TTSService)
    script = svc._build_script("Big news today", "Details about the story.")
    assert "Big news today" in script
    assert "Details about the story." in script


def test_build_script_uses_cta_when_provided() -> None:
    svc = object.__new__(TTSService)
    script = svc._build_script("Headline", "Summary", "Subscribe now")
    assert "Subscribe now" in script


def test_build_script_falls_back_to_default_cta() -> None:
    svc = object.__new__(TTSService)
    script = svc._build_script("Headline", "Summary", "")
    assert "Follow" in script


def test_build_script_no_summary_still_valid() -> None:
    svc = object.__new__(TTSService)
    script = svc._build_script("Breaking news", "", "")
    assert "Breaking news" in script
    assert len(script) > 0


# ---------------------------------------------------------------------------
# TTSService.generate_for_job
# ---------------------------------------------------------------------------

def _make_tts_service(provider=None) -> TTSService:
    svc = object.__new__(TTSService)
    svc.db = AsyncMock()
    svc.provider = provider or MockTTSProvider()
    return svc


@pytest.mark.asyncio
async def test_generate_for_job_creates_voiceover_asset() -> None:
    svc = _make_tts_service()
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()

    with patch("backend.modules.content_generation.tts_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = AsyncMock(return_value="http://storage/voiceover.wav")

        asset = await svc.generate_for_job(
            tenant_id=tenant_id,
            job_id=job_id,
            headline="Test headline",
            summary="Summary text",
            platform="x",
        )

    assert asset is not None
    assert asset.asset_type == GeneratedAssetType.VOICEOVER.value
    assert asset.platform == "x"
    assert asset.variant_label == "voiceover"
    assert asset.public_url == "http://storage/voiceover.wav"
    assert asset.mime_type == "audio/wav"
    assert asset.size_bytes > 0
    assert asset.checksum is not None
    assert asset.asset_metadata["tts_provider"] == "mock"
    svc.db.add.assert_called_once()
    svc.db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_for_job_returns_none_when_no_bytes() -> None:
    empty_provider = MagicMock(spec=MockTTSProvider)
    empty_provider.synthesize = AsyncMock(return_value=TTSResult(audio_bytes=b""))
    svc = _make_tts_service(provider=empty_provider)

    result = await svc.generate_for_job(
        tenant_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        headline="Test",
    )

    assert result is None
    svc.db.add.assert_not_called()


@pytest.mark.asyncio
async def test_generate_for_job_storage_failure_creates_asset_without_url() -> None:
    svc = _make_tts_service()

    with patch("backend.modules.content_generation.tts_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = AsyncMock(side_effect=Exception("MinIO down"))

        asset = await svc.generate_for_job(
            tenant_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            headline="Test",
        )

    assert asset is not None
    assert asset.public_url is None
    assert asset.storage_key is None
    assert asset.size_bytes > 0


@pytest.mark.asyncio
async def test_generate_for_job_storage_not_configured() -> None:
    svc = _make_tts_service()

    with patch("backend.modules.content_generation.tts_service.object_storage") as mock_storage:
        mock_storage.is_configured = False

        asset = await svc.generate_for_job(
            tenant_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            headline="Test",
        )

    assert asset is not None
    assert asset.public_url is None


@pytest.mark.asyncio
async def test_generate_for_job_storage_key_path() -> None:
    svc = _make_tts_service()
    tenant_id = uuid.uuid4()
    job_id = uuid.uuid4()
    captured_key: list[str] = []

    async def capture_upload(*, object_key, body, content_type):
        captured_key.append(object_key)
        return f"http://storage/{object_key}"

    with patch("backend.modules.content_generation.tts_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = capture_upload

        await svc.generate_for_job(
            tenant_id=tenant_id,
            job_id=job_id,
            headline="Test",
            platform="instagram",
        )

    assert len(captured_key) == 1
    key = captured_key[0]
    assert str(tenant_id) in key
    assert str(job_id) in key
    assert "instagram" in key
    assert key.endswith(".wav") or key.endswith(".mp3")


@pytest.mark.asyncio
async def test_generate_for_job_mp3_provider_uses_mp3_ext() -> None:
    """Providers that return audio/mpeg should create .mp3 storage keys."""
    mp3_provider = MagicMock(spec=OpenAITTSProvider)
    mp3_provider.synthesize = AsyncMock(
        return_value=TTSResult(
            audio_bytes=b"ID3" + b"\x00" * 50,
            mime_type="audio/mpeg",
            provider="openai",
            script_used="test",
        )
    )
    svc = _make_tts_service(provider=mp3_provider)
    captured_key: list[str] = []

    async def capture_upload(*, object_key, body, content_type):
        captured_key.append(object_key)
        return f"http://storage/{object_key}"

    with patch("backend.modules.content_generation.tts_service.object_storage") as mock_storage:
        mock_storage.is_configured = True
        mock_storage.upload_bytes = capture_upload

        await svc.generate_for_job(
            tenant_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            headline="Test",
        )

    assert captured_key[0].endswith(".mp3")


# ---------------------------------------------------------------------------
# Integration: ContentGenerationService.generate produces VOICEOVER asset
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_pipeline_produces_voiceover_asset() -> None:
    """generate() must call TTSService and produce a VOICEOVER asset."""
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
    plan.recommended_cta = "Follow us"
    svc.plan_repo.get_content_plan = AsyncMock(return_value=plan)

    cluster = MagicMock()
    cluster.id = uuid.uuid4()
    cluster.headline = "Test headline"
    cluster.summary = "Summary"
    cluster.primary_topic = "technology"
    cluster.explainability = {"keywords": "AI"}
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
    job.grounding_bundle = {"headline": "Test", "summary": "S", "topic": "t"}
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
    orch_result.writer.drafts = {"x": "Draft"}
    orch_result.optimizer.variants = []
    orch_result.optimizer.recommended_variant_index = 0
    orch_result.final_draft = "Draft"

    tts_calls: list[dict] = []

    async def fake_tts_generate(**kwargs):
        tts_calls.append(kwargs)
        asset = MagicMock(spec=GeneratedAsset)
        asset.asset_type = GeneratedAssetType.VOICEOVER.value
        return asset

    with (
        patch("backend.modules.content_generation.service.EditorialBriefRepository") as mock_brief_cls,
        patch("backend.modules.content_generation.service.ContentOrchestrator") as mock_orch_cls,
        patch("backend.modules.content_generation.image_service.ImageGenerationService") as mock_img_cls,
        patch("backend.modules.content_generation.tts_service.TTSService") as mock_tts_cls,
    ):
        mock_brief_cls.return_value.get_by_cluster = AsyncMock(return_value=brief)
        mock_orch = AsyncMock()
        mock_orch.run = AsyncMock(return_value=orch_result)
        mock_orch_cls.return_value = mock_orch
        mock_img_cls.return_value.generate_for_job = AsyncMock(return_value=MagicMock())
        mock_tts_instance = AsyncMock()
        mock_tts_instance.generate_for_job = AsyncMock(side_effect=fake_tts_generate)
        mock_tts_cls.return_value = mock_tts_instance

        await svc.generate(tenant_id=tenant_id, plan_id=plan.id)

    assert len(tts_calls) == 1
    call = tts_calls[0]
    assert call["tenant_id"] == tenant_id
    assert call["job_id"] == job.id
    assert call["headline"] == "Test headline"
    assert call["platform"] == "x"
    assert call["cta"] == "Follow us"
