from __future__ import annotations

from backend.modules.video_pipeline.schemas import RenderArtifacts, RendererInput


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
