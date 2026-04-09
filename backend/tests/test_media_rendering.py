from __future__ import annotations

import shutil
import wave
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.modules.content_generation.models import GeneratedAssetType, VideoStage
from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.video_pipeline.schemas import BrandingConfig, RenderArtifacts, RendererInput, RenderPreset
from backend.modules.video_pipeline.service import VideoPipelineService
from backend.modules.video_pipeline.providers import FFmpegRenderService


def test_renderer_input_payload_includes_branding_and_preset() -> None:
    svc = object.__new__(ContentGenerationService)
    profile = MagicMock()
    profile.visual_style = {
        "palette": "#111827,#2563eb,#f8fafc",
        "accent_color": "#22d3ee",
        "font_family": "Sans",
        "overlay_opacity": 0.42,
    }
    profile.default_cta = "Follow for updates"

    payload = svc._build_renderer_input_payload(
        platform="instagram",
        headline="Headline",
        summary="Summary",
        script="Line one. Line two. Line three.",
        cta="Follow for updates",
        talking_points=["Point A", "Point B"],
        profile=profile,
    )

    assert payload["preset"] == RenderPreset.SQUARE.value
    assert payload["branding"]["accent_color"] == "#22d3ee"
    assert payload["media_sequence"]
    assert payload["visual_segments"]


@pytest.mark.asyncio
async def test_video_pipeline_stores_preview_clip_asset() -> None:
    svc = object.__new__(VideoPipelineService)
    svc.db = AsyncMock()
    svc.db.add = MagicMock()
    svc.db.flush = AsyncMock()
    svc.content_repo = AsyncMock()
    svc.research_provider = MagicMock(build_digest=AsyncMock(return_value="digest"))
    svc.script_provider = MagicMock(build_script=AsyncMock(return_value="script line one\nscript line two"))
    svc.visual_provider = MagicMock(build_storyboard=AsyncMock(return_value="storyboard"))
    svc.voice_provider = MagicMock(synthesize=AsyncMock(return_value=b"voice"))
    svc.caption_provider = MagicMock(build_captions=AsyncMock(return_value="1\n00:00:00,000 --> 00:00:02,000\ncaption"))
    svc.render_service = MagicMock(
        render=AsyncMock(
            return_value=RenderArtifacts(
                video_bytes=b"video-bytes",
                preview_bytes=b"preview-bytes",
                thumbnail_bytes=b"thumb-bytes",
            )
        )
    )

    stored_assets: list[GeneratedAssetType] = []

    async def fake_store_asset(**kwargs):
        stored_assets.append(kwargs["asset_type"])
        asset = MagicMock()
        asset.asset_type = kwargs["asset_type"].value
        return asset

    svc._store_asset = AsyncMock(side_effect=fake_store_asset)
    svc._load_renderer_input = AsyncMock(return_value=None)

    job = MagicMock()
    job.id = uuid4()
    job.tenant_id = uuid4()
    job.stage = VideoStage.QUEUED.value
    job.progress = 0
    cluster = MagicMock()
    cluster.headline = "Headline"
    cluster.summary = "Summary"
    cluster.primary_topic = "topic"
    cluster.explainability = {"keywords": "topic, trend"}

    await svc.run(job=job, cluster=cluster)

    assert GeneratedAssetType.VIDEO in stored_assets
    assert GeneratedAssetType.PREVIEW_CLIP in stored_assets
    assert GeneratedAssetType.THUMBNAIL in stored_assets


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
@pytest.mark.asyncio
async def test_ffmpeg_render_service_smoke() -> None:
    with NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        with wave.open(str(temp_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\x00\x00" * 22050 * 2)
        voiceover_bytes = temp_path.read_bytes()
    finally:
        temp_path.unlink(missing_ok=True)

    service = FFmpegRenderService()
    renderer_input = RendererInput(
        platform="tiktok",
        script="Hook line. Detail line. CTA line.",
        subtitles=["Hook line", "Detail line", "CTA line"],
        voiceover_script="Hook line. Detail line. CTA line.",
        title_card="Hook line",
        summary_card="Detail line",
        cta="CTA line",
        branding=BrandingConfig(progress_bar=True, subtitle_burn_in=True),
        preset=RenderPreset.VERTICAL,
    )

    artifacts = await service.render(
        renderer_input=renderer_input,
        captions="1\n00:00:00,000 --> 00:00:02,000\nHook line",
        voiceover_bytes=voiceover_bytes,
    )

    assert len(artifacts.video_bytes) > 0
    assert len(artifacts.preview_bytes) > 0
    assert len(artifacts.thumbnail_bytes) > 0
