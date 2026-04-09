from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.storage import object_storage
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.models import ContentJob, GeneratedAsset, GeneratedAssetType, VideoStage
from backend.modules.story_intelligence.models import StoryCluster
from backend.modules.video_pipeline.providers import get_video_providers
from backend.modules.video_pipeline.schemas import BrandingConfig, RendererInput


class VideoPipelineService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.content_repo = ContentGenerationRepository(db)
        (
            self.research_provider,
            self.script_provider,
            self.visual_provider,
            self.voice_provider,
            self.caption_provider,
            self.render_service,
        ) = get_video_providers()

    async def _store_asset(
        self,
        *,
        tenant_id,
        content_job_id,
        asset_type: GeneratedAssetType,
        text_content: str | None = None,
        binary_content: bytes | None = None,
        filename: str | None = None,
        mime_type: str = "text/plain",
    ) -> GeneratedAsset:
        storage_key = None
        public_url = None
        size_bytes = None
        if binary_content is not None and filename is not None:
            storage_key = f"tenants/{tenant_id}/assets/{content_job_id}/{filename}"
            public_url = await object_storage.upload_bytes(
                object_key=storage_key,
                body=binary_content,
                content_type=mime_type,
            )
            size_bytes = len(binary_content)
        asset = GeneratedAsset(
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            asset_type=asset_type.value,
            storage_key=storage_key,
            public_url=public_url,
            mime_type=mime_type,
            size_bytes=size_bytes,
            text_content=text_content,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def _load_renderer_input(self, job_id) -> RendererInput | None:
        assets = await self.content_repo.list_assets(job_id)
        renderer_assets = [
            asset for asset in assets if asset.asset_type == GeneratedAssetType.RENDERER_INPUT.value or asset.asset_type == GeneratedAssetType.RENDERER_INPUT
        ]
        if not renderer_assets:
            return None
        selected = renderer_assets[0]
        if not selected.text_content:
            return None
        return RendererInput.model_validate_json(selected.text_content)

    async def run(self, *, job: ContentJob, cluster: StoryCluster) -> list[GeneratedAsset]:
        article_points = [cluster.summary, cluster.explainability.get("keywords", "")]
        assets: list[GeneratedAsset] = []
        renderer_input = await self._load_renderer_input(job.id)

        job.stage = VideoStage.RESEARCHING.value
        job.progress = 10
        digest = await self.research_provider.build_digest(cluster.headline, cluster.summary, article_points)
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.RESEARCH_DIGEST,
                text_content=digest,
            )
        )

        job.stage = VideoStage.SCRIPTING.value
        job.progress = 25
        script = (
            renderer_input.voiceover_script if renderer_input and renderer_input.voiceover_script
            else await self.script_provider.build_script(digest, tone="urgent")
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.SCRIPT,
                text_content=script,
            )
        )

        job.stage = VideoStage.PLANNING.value
        job.progress = 40
        storyboard = (
            "\n".join(
                f"Scene {segment.segment}: {segment.prompt}"
                for segment in (renderer_input.visual_segments if renderer_input else [])
            )
            or await self.visual_provider.build_storyboard(script)
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.STORYBOARD,
                text_content=storyboard,
            )
        )

        job.stage = VideoStage.GENERATING_VOICE.value
        job.progress = 55
        voiceover = await self.voice_provider.synthesize(script)
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.VOICEOVER,
                binary_content=voiceover,
                filename="voiceover.wav",
                mime_type="audio/wav",
            )
        )

        job.stage = VideoStage.CAPTIONING.value
        job.progress = 70
        captions = (
            self._srt_from_lines(renderer_input.subtitles)
            if renderer_input and renderer_input.subtitles
            else await self.caption_provider.build_captions(script)
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.CAPTION,
                text_content=captions,
                filename="captions.srt",
            )
        )

        job.stage = VideoStage.RENDERING.value
        job.progress = 85
        effective_renderer_input = renderer_input or RendererInput(
            platform="tiktok",
            script=script,
            subtitles=[line for line in script.splitlines() if line.strip()][:6],
            voiceover_script=script,
            title_card=cluster.headline,
            summary_card=cluster.summary,
            cta="Follow for the next development.",
            branding=BrandingConfig(intro_text=cluster.headline, outro_text="Follow for the next development."),
        )
        render_artifacts = await self.render_service.render(
            renderer_input=effective_renderer_input,
            captions=captions,
            voiceover_bytes=voiceover,
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.VIDEO,
                binary_content=render_artifacts.video_bytes,
                filename="video.mp4",
                mime_type="video/mp4",
            )
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.PREVIEW_CLIP,
                binary_content=render_artifacts.preview_bytes,
                filename="preview.mp4",
                mime_type="video/mp4",
            )
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.THUMBNAIL,
                binary_content=render_artifacts.thumbnail_bytes,
                filename="thumbnail.png",
                mime_type="image/png",
            )
        )

        job.stage = VideoStage.PACKAGING.value
        job.progress = 100
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.METADATA,
                text_content=f"headline={cluster.headline}\nprimary_topic={cluster.primary_topic}",
            )
        )
        return assets

    @staticmethod
    def _srt_from_lines(lines: list[str]) -> str:
        blocks: list[str] = []
        for index, line in enumerate(lines[:8], start=1):
            start = (index - 1) * 2
            end = start + 2
            blocks.append(
                f"{index}\n00:00:{start:02d},000 --> 00:00:{end:02d},000\n{line}"
            )
        return "\n\n".join(blocks)
