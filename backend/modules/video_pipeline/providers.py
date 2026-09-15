from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from backend.modules.inference.providers import get_llm_provider
from backend.modules.video_pipeline.ffmpeg_render import FFmpegRenderService
from backend.modules.video_pipeline.provider_base import (
    CaptionProvider,
    RenderService,
    ResearchProvider,
    ScriptProvider,
    VisualProvider,
    VoiceProvider,
)

__all__ = [
    "CaptionProvider",
    "FFmpegRenderService",
    "MockCaptionProvider",
    "MockResearchProvider",
    "MockScriptProvider",
    "MockVisualProvider",
    "MockVoiceProvider",
    "RenderService",
    "ResearchProvider",
    "ScriptProvider",
    "VisualProvider",
    "VoiceProvider",
    "get_video_providers",
]


class MockResearchProvider(ResearchProvider):
    async def build_digest(self, headline: str, summary: str, article_points: list[str]) -> str:
        return "\n".join(
            [
                f"Headline: {headline}",
                f"Summary: {summary}",
                "Key points:",
                *[f"- {point}" for point in article_points[:5]],
            ]
        )


class MockScriptProvider(ScriptProvider):
    def __init__(self) -> None:
        self.llm = get_llm_provider()

    async def build_script(self, digest: str, tone: str) -> str:
        summary = await self.llm.summarize(f"Tone: {tone}\n{digest}", max_words=120)
        return (
            "Hook: Stop scrolling, here is the signal you need right now.\n"
            f"{summary}\n"
            "CTA: Follow for the next development."
        )


class MockVisualProvider(VisualProvider):
    async def build_storyboard(self, script: str) -> str:
        scenes = [line.strip() for line in script.splitlines() if line.strip()]
        return "\n".join(f"Scene {index + 1}: {scene}" for index, scene in enumerate(scenes[:5]))


class MockVoiceProvider(VoiceProvider):
    async def synthesize(self, script: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".wav") as temp_file:
            with wave.open(temp_file.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                wav_file.writeframes(b"\x00\x00" * 22050 * 3)
            return Path(temp_file.name).read_bytes()


class MockCaptionProvider(CaptionProvider):
    async def build_captions(self, script: str) -> str:
        lines = [line.strip() for line in script.splitlines() if line.strip()]
        captions = ["1", "00:00:00,000 --> 00:00:03,000", lines[0] if lines else "Signal update"]
        if len(lines) > 1:
            captions.extend(["", "2", "00:00:03,000 --> 00:00:07,000", " ".join(lines[1:3])[:120]])
        return "\n".join(captions)


def get_video_providers() -> tuple[
    ResearchProvider, ScriptProvider, VisualProvider, VoiceProvider, CaptionProvider, RenderService
]:
    return (
        MockResearchProvider(),
        MockScriptProvider(),
        MockVisualProvider(),
        MockVoiceProvider(),
        MockCaptionProvider(),
        FFmpegRenderService(),
    )
