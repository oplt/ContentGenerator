"""
ImageGenerationService — generates a cover image for a content job and stores
it in object storage (MinIO/S3) as a GeneratedAsset (type=THUMBNAIL).

Prompt strategy
---------------
  "{primary_topic}, {keywords}, editorial photography, sharp focus,
   high resolution, professional news image"

Storage path
------------
  tenants/{tenant_id}/assets/{content_job_id}/cover_{platform}.png
"""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.storage import object_storage
from backend.modules.content_generation.image_providers import (
    ImageGenerationProvider,
    get_image_provider,
)
from backend.modules.content_generation.models import (
    GeneratedAsset,
    GeneratedAssetType,
)

logger = logging.getLogger(__name__)


class ImageGenerationService:
    def __init__(self, db: AsyncSession, provider: ImageGenerationProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_image_provider()

    def _build_prompt(self, headline: str, primary_topic: str, keywords: str) -> str:
        parts = [primary_topic.strip()]
        if keywords:
            parts.append(keywords.strip())
        parts.append("editorial photography, sharp focus, high resolution, professional news image")
        return ", ".join(parts)[:400]

    async def generate_for_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        headline: str,
        primary_topic: str,
        keywords: str = "",
        platform: str = "default",
    ) -> GeneratedAsset | None:
        """
        Generate a cover image and persist it as a THUMBNAIL asset.

        Returns the created GeneratedAsset, or None if generation produced no bytes
        (e.g. provider is unreachable and no fallback bytes were emitted).
        """
        prompt = self._build_prompt(headline, primary_topic, keywords)
        result = await self.provider.generate(prompt)

        if not result.image_bytes:
            logger.info(
                "image_generation_skipped: provider=%s produced no bytes for job=%s",
                result.provider,
                job_id,
            )
            return None

        storage_key: str | None = None
        public_url: str | None = None
        size_bytes = len(result.image_bytes)
        checksum = hashlib.sha256(result.image_bytes).hexdigest()

        if object_storage.is_configured:
            try:
                storage_key = (
                    f"tenants/{tenant_id}/assets/{job_id}/cover_{platform}.png"
                )
                public_url = await object_storage.upload_bytes(
                    object_key=storage_key,
                    body=result.image_bytes,
                    content_type=result.mime_type,
                )
            except Exception as exc:
                logger.warning(
                    "image_storage_upload_failed job=%s error=%s", job_id, exc
                )
                # Still create the asset record without a public URL
                storage_key = None

        asset = GeneratedAsset(
            tenant_id=tenant_id,
            content_job_id=job_id,
            asset_type=GeneratedAssetType.THUMBNAIL.value,
            platform=platform,
            variant_label="cover",
            storage_key=storage_key,
            public_url=public_url,
            mime_type=result.mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            asset_metadata={
                "image_provider": result.provider,
                "width": str(result.width),
                "height": str(result.height),
            },
            source_trace={"prompt": result.prompt_used},
        )
        self.db.add(asset)
        await self.db.flush()
        return asset
