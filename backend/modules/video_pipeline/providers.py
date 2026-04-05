from __future__ import annotations

import contextlib
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

from backend.core.config import settings
from backend.modules.story_intelligence.providers import get_llm_provider


class ResearchProvider:
    async def build_digest(self, headline: str, summary: str, article_points: list[str]) -> str:
        raise NotImplementedError


class ScriptProvider:
    async def build_script(self, digest: str, tone: str) -> str:
        raise NotImplementedError


class VisualProvider:
    async def build_storyboard(self, script: str) -> str:
        raise NotImplementedError


class VoiceProvider:
    async def synthesize(self, script: str) -> bytes:
        raise NotImplementedError


class CaptionProvider:
    async def build_captions(self, script: str) -> str:
        raise NotImplementedError


class RenderService:
    async def render(
        self,
        *,
        headline: str,
        script: str,
        captions: str,
        voiceover_bytes: bytes,
    ) -> tuple[bytes, bytes]:
        raise NotImplementedError


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


class FFmpegRenderService(RenderService):
    async def render(
        self,
        *,
        headline: str,
        script: str,
        captions: str,
        voiceover_bytes: bytes,
    ) -> tuple[bytes, bytes]:
        safe_text = headline.replace(":", "").replace("'", "")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            audio_path = temp_path / f"{uuid4()}.wav"
            video_path = temp_path / f"{uuid4()}.mp4"
            thumb_path = temp_path / f"{uuid4()}.png"
            audio_path.write_bytes(voiceover_bytes)
            command = [
                settings.FFMPEG_BIN,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x0f172a:s=1080x1920:d=8",
                "-i",
                str(audio_path),
                "-shortest",
                "-vf",
                f"drawtext=text='{safe_text[:60]}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                str(video_path),
            ]
            with contextlib.suppress(Exception):
                subprocess.run(command, check=True, capture_output=True)
            if not video_path.exists():
                subprocess.run(
                    [
                        settings.FFMPEG_BIN,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=0x0f172a:s=1080x1920:d=8",
                        str(video_path),
                    ],
                    check=True,
                    capture_output=True,
                )
            subprocess.run(
                [
                    settings.FFMPEG_BIN,
                    "-y",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    str(thumb_path),
                ],
                check=True,
                capture_output=True,
            )
            return video_path.read_bytes(), thumb_path.read_bytes()


def get_video_providers() -> tuple[ResearchProvider, ScriptProvider, VisualProvider, VoiceProvider, CaptionProvider, RenderService]:
    return (
        MockResearchProvider(),
        MockScriptProvider(),
        MockVisualProvider(),
        MockVoiceProvider(),
        MockCaptionProvider(),
        FFmpegRenderService(),
    )
