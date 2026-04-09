"""
TTSService — converts a content job's headline + summary into a voiceover
and stores it as a VOICEOVER GeneratedAsset in object storage (MinIO/S3).

Script format
-------------
  {headline}.

  {summary}

  Follow for more updates.

Storage path
------------
  tenants/{tenant_id}/assets/{job_id}/voiceover_{platform}.{ext}
"""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.storage import object_storage
from backend.modules.content_generation.models import (
    GeneratedAsset,
    GeneratedAssetType,
)
from backend.modules.content_generation.tts_providers import (
    TTSProvider,
    get_tts_provider,
)

logger = logging.getLogger(__name__)

# Extension map for known MIME types
_MIME_TO_EXT: dict[str, str] = {
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
    "audio/ogg": "ogg",
}


class TTSService:
    def __init__(self, db: AsyncSession, provider: TTSProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_tts_provider()

    def _build_script(self, headline: str, summary: str, cta: str = "") -> str:
        parts = [headline.strip()]
        if summary.strip():
            parts.append(summary.strip())
        parts.append(cta.strip() if cta.strip() else "Follow for more updates.")
        return "\n\n".join(parts)

    async def generate_for_job(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        headline: str,
        summary: str = "",
        cta: str = "",
        platform: str = "default",
    ) -> GeneratedAsset | None:
        """
        Synthesize speech and persist it as a VOICEOVER asset.

        Returns the GeneratedAsset, or None if the provider emits no bytes.
        """
        script = self._build_script(headline, summary, cta)
        result = await self.provider.synthesize(script)

        if not result.audio_bytes:
            logger.info(
                "tts_generation_skipped: provider=%s produced no bytes for job=%s",
                result.provider,
                job_id,
            )
            return None

        ext = _MIME_TO_EXT.get(result.mime_type, "wav")
        size_bytes = len(result.audio_bytes)
        checksum = hashlib.sha256(result.audio_bytes).hexdigest()

        storage_key: str | None = None
        public_url: str | None = None

        if object_storage.is_configured:
            try:
                storage_key = (
                    f"tenants/{tenant_id}/assets/{job_id}/voiceover_{platform}.{ext}"
                )
                public_url = await object_storage.upload_bytes(
                    object_key=storage_key,
                    body=result.audio_bytes,
                    content_type=result.mime_type,
                )
            except Exception as exc:
                logger.warning(
                    "tts_storage_upload_failed job=%s error=%s", job_id, exc
                )
                storage_key = None

        asset = GeneratedAsset(
            tenant_id=tenant_id,
            content_job_id=job_id,
            asset_type=GeneratedAssetType.VOICEOVER.value,
            platform=platform,
            variant_label="voiceover",
            storage_key=storage_key,
            public_url=public_url,
            mime_type=result.mime_type,
            size_bytes=size_bytes,
            checksum=checksum,
            asset_metadata={
                "tts_provider": result.provider,
                "audio_format": ext,
            },
            source_trace={"script": result.script_used[:500]},
        )
        self.db.add(asset)
        await self.db.flush()
        return asset
