from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.storage import object_storage
from backend.modules.content_generation.models import ContentJob, GeneratedAsset, GeneratedAssetType, VideoStage
from backend.modules.story_intelligence.models import StoryCluster
from backend.modules.video_pipeline.providers import get_video_providers


class VideoPipelineService:
    def __init__(self, db: AsyncSession):
        self.db = db
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

    async def run(self, *, job: ContentJob, cluster: StoryCluster) -> list[GeneratedAsset]:
        article_points = [cluster.summary, cluster.explainability.get("keywords", "")]
        assets: list[GeneratedAsset] = []

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
        script = await self.script_provider.build_script(digest, tone="urgent")
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
        storyboard = await self.visual_provider.build_storyboard(script)
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
        captions = await self.caption_provider.build_captions(script)
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
        video_bytes, thumbnail_bytes = await self.render_service.render(
            headline=cluster.headline,
            script=script,
            captions=captions,
            voiceover_bytes=voiceover,
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.VIDEO,
                binary_content=video_bytes,
                filename="video.mp4",
                mime_type="video/mp4",
            )
        )
        assets.append(
            await self._store_asset(
                tenant_id=job.tenant_id,
                content_job_id=job.id,
                asset_type=GeneratedAssetType.THUMBNAIL,
                binary_content=thumbnail_bytes,
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
