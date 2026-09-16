"""Durable ContentVariant persist/load for PlatformTransform → Publish (Phase 10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.models import ContentVariant, ContentVariantTarget


def _snapshot_from_row(
    variant: ContentVariant,
    targets: list[ContentVariantTarget],
) -> VariantSnapshot:
    return VariantSnapshot(
        variant_id=variant.id,
        content_job_id=variant.content_job_id,
        fingerprint=variant.fingerprint,
        platform=variant.platform,
        text=variant.text,
        title=variant.title,
        description=variant.description,
        tags=tuple(variant.tags or []),
        media_refs=tuple(variant.media_refs or []),
        social_account_ids=tuple(t.social_account_id for t in targets),
    )


@dataclass(frozen=True, slots=True)
class VariantSnapshot:
    """Immutable publish payload derived from a ContentVariant row."""

    variant_id: UUID
    content_job_id: UUID
    fingerprint: str
    platform: str
    text: str
    title: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    media_refs: tuple[dict[str, object], ...] = ()
    social_account_ids: tuple[UUID, ...] = ()

    def as_provider_payload(self) -> dict[str, str]:
        """String-valued snapshot for PublishingJob.provider_payload (immutable intent)."""
        return {
            "content_variant_id": str(self.variant_id),
            "variant_fingerprint": self.fingerprint,
            "variant_platform": self.platform,
            "variant_text": self.text,
            "variant_title": self.title or "",
            "variant_description": self.description or "",
            "variant_tags": ",".join(self.tags),
            "variant_source": "content_variant",
        }


@dataclass
class VariantPublishAsset:
    """GeneratedAsset-shaped view so providers can consume variant text."""

    asset_type: str = "text_variant"
    platform: str | None = None
    text_content: str | None = None
    public_url: str | None = None
    mime_type: str = "text/plain"
    asset_metadata: dict[str, Any] = field(default_factory=dict)
    storage_key: str | None = None
    size_bytes: int | None = None


def assets_from_variant_snapshot(
    snapshot: VariantSnapshot,
    *,
    media_assets: list[Any] | None = None,
) -> list[Any]:
    """Prefer variant text; keep non-text GeneratedAssets (video/image) from the job."""
    text_asset = VariantPublishAsset(
        asset_type="text_variant",
        platform=snapshot.platform,
        text_content=snapshot.text,
        asset_metadata={
            "content_variant_id": str(snapshot.variant_id),
            "fingerprint": snapshot.fingerprint,
            "title": snapshot.title or "",
            "description": snapshot.description or "",
            "tags": list(snapshot.tags),
        },
    )
    media: list[Any] = []
    for asset in media_assets or []:
        asset_type = str(getattr(asset, "asset_type", "") or "")
        if asset_type in {"text_variant", "text"}:
            continue
        media.append(asset)
    return [text_asset, *media]


def snapshot_from_provider_payload(payload: dict[str, Any] | None) -> VariantSnapshot | None:
    """Rebuild a minimal snapshot from an immutable job provider_payload."""
    raw = dict(payload or {})
    if str(raw.get("variant_source") or "") != "content_variant":
        return None
    variant_id_raw = raw.get("content_variant_id") or ""
    text = str(raw.get("variant_text") or "").strip()
    if not variant_id_raw or not text:
        return None
    try:
        variant_id = UUID(str(variant_id_raw))
    except ValueError:
        return None
    tags_raw = str(raw.get("variant_tags") or "")
    tags = tuple(t for t in tags_raw.split(",") if t)
    return VariantSnapshot(
        variant_id=variant_id,
        content_job_id=UUID(int=0),  # not needed for publish text path
        fingerprint=str(raw.get("variant_fingerprint") or ""),
        platform=str(raw.get("variant_platform") or ""),
        text=text,
        title=str(raw.get("variant_title") or "") or None,
        description=str(raw.get("variant_description") or "") or None,
        tags=tags,
    )


class ContentVariantStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_variant(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        fingerprint: str,
        platform: str,
        text: str,
        social_account_ids: list[UUID],
        workflow_run_id: UUID | None = None,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        media_refs: list[dict[str, object]] | None = None,
    ) -> ContentVariant:
        existing = await self.get_by_fingerprint(
            tenant_id=tenant_id,
            content_job_id=content_job_id,
            fingerprint=fingerprint,
        )
        if existing is None:
            existing = ContentVariant(
                tenant_id=tenant_id,
                content_job_id=content_job_id,
                workflow_run_id=workflow_run_id,
                fingerprint=fingerprint,
                platform=platform,
                text=text,
                title=title,
                description=description,
                tags=list(tags or []),
                media_refs=list(media_refs or []),
            )
            self.db.add(existing)
            await self.db.flush()
        else:
            existing.platform = platform
            existing.text = text
            existing.title = title
            existing.description = description
            existing.tags = list(tags or [])
            existing.media_refs = list(media_refs or [])
            if workflow_run_id is not None:
                existing.workflow_run_id = workflow_run_id
            await self.db.flush()

        await self._sync_targets(
            tenant_id=tenant_id,
            variant_id=existing.id,
            social_account_ids=social_account_ids,
        )
        return existing

    async def _sync_targets(
        self,
        *,
        tenant_id: UUID,
        variant_id: UUID,
        social_account_ids: list[UUID],
    ) -> None:
        result = await self.db.execute(
            select(ContentVariantTarget).where(ContentVariantTarget.variant_id == variant_id)
        )
        existing_rows = list(result.scalars().all())
        existing_ids = {row.social_account_id for row in existing_rows}
        wanted = set(social_account_ids)
        for row in existing_rows:
            if row.social_account_id not in wanted:
                await self.db.delete(row)
        for account_id in wanted - existing_ids:
            self.db.add(
                ContentVariantTarget(
                    tenant_id=tenant_id,
                    variant_id=variant_id,
                    social_account_id=account_id,
                )
            )
        await self.db.flush()

    async def get_by_fingerprint(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        fingerprint: str,
    ) -> ContentVariant | None:
        result = await self.db.execute(
            select(ContentVariant).where(
                ContentVariant.tenant_id == tenant_id,
                ContentVariant.content_job_id == content_job_id,
                ContentVariant.fingerprint == fingerprint,
                ContentVariant.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def get_variant(
        self, tenant_id: UUID, variant_id: UUID
    ) -> ContentVariant | None:
        result = await self.db.execute(
            select(ContentVariant).where(
                ContentVariant.id == variant_id,
                ContentVariant.tenant_id == tenant_id,
                ContentVariant.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_for_job(
        self, tenant_id: UUID, content_job_id: UUID
    ) -> list[ContentVariant]:
        result = await self.db.execute(
            select(ContentVariant)
            .where(
                ContentVariant.tenant_id == tenant_id,
                ContentVariant.content_job_id == content_job_id,
                ContentVariant.deleted_at.is_(None),
            )
            .order_by(ContentVariant.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_targets(self, variant_id: UUID) -> list[ContentVariantTarget]:
        result = await self.db.execute(
            select(ContentVariantTarget).where(ContentVariantTarget.variant_id == variant_id)
        )
        return list(result.scalars().all())

    async def get_snapshot(
        self, tenant_id: UUID, variant_id: UUID
    ) -> VariantSnapshot | None:
        variant = await self.get_variant(tenant_id, variant_id)
        if variant is None:
            return None
        return _snapshot_from_row(variant, await self.list_targets(variant.id))

    async def resolve_for_account(
        self,
        *,
        tenant_id: UUID,
        content_job_id: UUID,
        social_account_id: UUID,
        preferred_variant_ids: list[UUID] | None = None,
    ) -> VariantSnapshot | None:
        """Pick the variant targeting this account (optional preferred id filter)."""
        preferred = list(preferred_variant_ids or [])
        if preferred:
            for variant_id in preferred:
                snap = await self.get_snapshot(tenant_id, variant_id)
                if snap is None or snap.content_job_id != content_job_id:
                    continue
                if social_account_id in snap.social_account_ids:
                    return snap
            return None

        for variant in await self.list_for_job(tenant_id, content_job_id):
            targets = await self.list_targets(variant.id)
            if social_account_id in {t.social_account_id for t in targets}:
                return _snapshot_from_row(variant, targets)
        return None
