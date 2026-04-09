from __future__ import annotations

import contextlib
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4

from backend.core.config import settings
from backend.modules.inference.providers import get_llm_provider
from backend.modules.video_pipeline.schemas import BrandingConfig, MediaSequenceItem, RenderArtifacts, RendererInput, RenderPreset


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
        renderer_input: RendererInput,
        captions: str,
        voiceover_bytes: bytes,
    ) -> RenderArtifacts:
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
    def _dimensions(self, preset: RenderPreset) -> tuple[int, int]:
        if preset == RenderPreset.SQUARE:
            return (1080, 1080)
        if preset == RenderPreset.HORIZONTAL:
            return (1920, 1080)
        return (1080, 1920)

    def _safe_drawtext(self, text: str) -> str:
        sanitized = re.sub(r"[\r\n]+", " ", text).strip()
        return sanitized.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")

    def _run_ffmpeg(self, args: list[str]) -> None:
        subprocess.run(args, check=True, capture_output=True)

    def _create_segment_clip(
        self,
        *,
        item: MediaSequenceItem,
        index: int,
        temp_path: Path,
        dimensions: tuple[int, int],
        branding: BrandingConfig,
    ) -> Path:
        width, height = dimensions
        clip_path = temp_path / f"segment_{index}.mp4"
        font_size = max(34, min(width, height) // 18)
        overlay_y = int(height * 0.18)
        background = item.background_color.lstrip("#") or "0f172a"
        if item.source_path and Path(item.source_path).exists():
            source = Path(item.source_path)
            if source.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}:
                cmd = [
                    settings.FFMPEG_BIN,
                    "-y",
                    "-i",
                    str(source),
                    "-t",
                    str(item.duration_seconds),
                    "-vf",
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                    "-an",
                    str(clip_path),
                ]
            else:
                cmd = [
                    settings.FFMPEG_BIN,
                    "-y",
                    "-loop",
                    "1",
                    "-i",
                    str(source),
                    "-t",
                    str(item.duration_seconds),
                    "-vf",
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                    "-an",
                    str(clip_path),
                ]
        else:
            text = self._safe_drawtext(item.text)
            alpha = max(0.05, min(branding.overlay_opacity, 0.9))
            vf = (
                f"drawbox=x=0:y=0:w={width}:h={height}:color={background}@1:t=fill,"
                f"drawbox=x={int(width*0.08)}:y={overlay_y}:w={int(width*0.84)}:h={int(height*0.24)}:color=black@{alpha}:t=fill,"
                f"drawtext=text='{text[:120]}':fontcolor={branding.text_color}:fontsize={font_size}:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"
            )
            cmd = [
                settings.FFMPEG_BIN,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x{background}:s={width}x{height}:d={item.duration_seconds}",
                "-vf",
                vf,
                "-an",
                str(clip_path),
            ]
        self._run_ffmpeg(cmd)
        return clip_path

    def _concat_segments(self, segment_paths: list[Path], concat_file: Path, output_path: Path) -> None:
        concat_file.write_text(
            "\n".join(f"file '{segment_path.as_posix()}'" for segment_path in segment_paths),
            encoding="utf-8",
        )
        self._run_ffmpeg(
            [
                settings.FFMPEG_BIN,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ]
        )

    def _build_video_filter(
        self,
        *,
        renderer_input: RendererInput,
        duration: float,
        subtitle_path: Path | None,
    ) -> str:
        width, height = self._dimensions(renderer_input.preset)
        filters: list[str] = []
        if renderer_input.branding.progress_bar:
            filters.append(
                "drawbox="
                f"x=0:y={height-24}:w='min(w,max(0,w*(t/{max(duration, 0.1)})))':h=24:"
                f"color={renderer_input.branding.accent_color}@0.95:t=fill"
            )
        if subtitle_path and renderer_input.branding.subtitle_burn_in:
            filters.append(f"subtitles={subtitle_path.as_posix()}")
        return ",".join(filters) if filters else "null"

    async def render(
        self,
        *,
        renderer_input: RendererInput,
        captions: str,
        voiceover_bytes: bytes,
    ) -> RenderArtifacts:
        dimensions = self._dimensions(renderer_input.preset)
        media_sequence = renderer_input.media_sequence or [
            MediaSequenceItem(kind="title", duration_seconds=renderer_input.output_duration_seconds, text=renderer_input.title_card or renderer_input.script)
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            audio_path = temp_path / f"{uuid4()}.wav"
            base_video_path = temp_path / f"{uuid4()}_base.mp4"
            video_path = temp_path / f"{uuid4()}.mp4"
            preview_path = temp_path / f"{uuid4()}_preview.mp4"
            thumb_path = temp_path / f"{uuid4()}.png"
            captions_path = temp_path / f"{uuid4()}.srt"
            concat_manifest = temp_path / "segments.txt"
            audio_path.write_bytes(voiceover_bytes)
            captions_path.write_text(captions, encoding="utf-8")
            segment_paths = [
                self._create_segment_clip(
                    item=item,
                    index=index,
                    temp_path=temp_path,
                    dimensions=dimensions,
                    branding=renderer_input.branding,
                )
                for index, item in enumerate(media_sequence, start=1)
            ]
            self._concat_segments(segment_paths, concat_manifest, base_video_path)
            video_filter = self._build_video_filter(
                renderer_input=renderer_input,
                duration=renderer_input.output_duration_seconds,
                subtitle_path=captions_path if captions.strip() else None,
            )
            with contextlib.suppress(Exception):
                self._run_ffmpeg(
                    [
                        settings.FFMPEG_BIN,
                        "-y",
                        "-i",
                        str(base_video_path),
                        "-i",
                        str(audio_path),
                        "-vf",
                        video_filter,
                        "-shortest",
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        str(video_path),
                    ]
                )
            if not video_path.exists():
                self._run_ffmpeg(
                    [
                        settings.FFMPEG_BIN,
                        "-y",
                        "-i",
                        str(base_video_path),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        str(video_path),
                    ]
                )
            self._run_ffmpeg(
                [
                    settings.FFMPEG_BIN,
                    "-y",
                    "-i",
                    str(video_path),
                    "-t",
                    str(min(renderer_input.preview_duration_seconds, renderer_input.output_duration_seconds)),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(preview_path),
                ]
            )
            self._run_ffmpeg(
                [
                    settings.FFMPEG_BIN,
                    "-y",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    str(thumb_path),
                ]
            )
            return RenderArtifacts(
                video_bytes=video_path.read_bytes(),
                preview_bytes=preview_path.read_bytes(),
                thumbnail_bytes=thumb_path.read_bytes(),
            )


def get_video_providers() -> tuple[ResearchProvider, ScriptProvider, VisualProvider, VoiceProvider, CaptionProvider, RenderService]:
    return (
        MockResearchProvider(),
        MockScriptProvider(),
        MockVisualProvider(),
        MockVoiceProvider(),
        MockCaptionProvider(),
        FFmpegRenderService(),
    )
