from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.core.config import settings
from backend.core.http import request
from backend.modules.content_generation.models import GeneratedAsset
from backend.modules.publishing.models import SocialAccount
from backend.modules.publishing.provider_base import (
    AuthValidationResult,
    DeletionResult,
    DraftResult,
    PublishResult,
    PublishingProvider,
)

_BSKY_PDS_BASE = settings.BLUESKY_PDS_URL.rstrip("/")
_MEDIA_ASSET_TYPES = {"image", "thumbnail"}


class BlueskyPublishingProvider(PublishingProvider):
    """
    Publishes to Bluesky via AT Protocol (app.bsky.feed.post).
    Auth: uses stored access token (app password or oauth session token).
    """
    platform = "bluesky"

    def __init__(self, access_token: str, did: str, dry_run: bool = False):
        self.access_token = access_token
        self.did = did  # Decentralised Identifier, e.g. did:plc:xxxxx
        self.dry_run = dry_run

    def capabilities(self) -> dict[str, str]:
        return {
            "text": "true",
            "video": "false",
            "rich_text": "true",
            "mode": "atproto",
            "native_scheduling": "false",
            "delete": "true",
        }

    async def validate_auth(self, *, social_account: SocialAccount) -> AuthValidationResult:
        is_valid = bool(self.access_token and self.did)
        return AuthValidationResult(
            is_valid=is_valid,
            account_status="connected" if is_valid else "needs_reauth",
            detail="atproto_credentials_present" if is_valid else "missing_access_token_or_did",
        )

    def _select_text(self, assets: list[GeneratedAsset]) -> str:
        for asset in assets:
            if asset.asset_type == "text_variant" and asset.text_content:
                return asset.text_content.strip()[:300]  # Bluesky grapheme limit ~300
        return ""

    def _media_assets(self, assets: list[GeneratedAsset]) -> list[GeneratedAsset]:
        return [
            a for a in assets
            if a.asset_type in _MEDIA_ASSET_TYPES
            and a.public_url
        ]

    async def _upload_blob(self, asset: GeneratedAsset) -> dict | None:
        """
        Download asset bytes and upload as an AT Protocol blob.
        Returns the blob ref dict on success, None on failure (best-effort).
        """
        if not asset.public_url:
            return None
        try:
            dl = await request("GET", asset.public_url, provider="publishing")
            dl.raise_for_status()
            resp = await request(
                "POST",
                f"{_BSKY_PDS_BASE}/xrpc/com.atproto.repo.uploadBlob",
                provider="publishing",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": asset.mime_type or "application/octet-stream",
                },
                content=dl.content,
            )
            resp.raise_for_status()
            return resp.json().get("blob")
        except Exception:
            return None

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        return await self.publish_now(social_account=social_account, assets=assets)

    async def publish_now(
        self,
        *,
        social_account: SocialAccount,
        assets: list[GeneratedAsset],
        publish_attempt_key: str = "",
    ) -> PublishResult:
        if self.dry_run:
            cid = f"dry-run-{uuid4()}"
            return PublishResult(
                status="succeeded_dry_run",
                external_post_id=cid,
                external_post_url=f"https://bsky.app/profile/{self.did}/post/{cid}",
                payload={"mode": "dry_run"},
            )

        text = self._select_text(assets)
        record: dict = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        # Upload image blobs and attach as embed (best-effort)
        blob_refs: list[dict] = []
        for asset in self._media_assets(assets):
            blob = await self._upload_blob(asset)
            if blob:
                blob_refs.append({"alt": "", "image": blob})

        if blob_refs:
            record["embed"] = {
                "$type": "app.bsky.embed.images",
                "images": blob_refs,
            }

        response = await request(
            "POST",
            f"{_BSKY_PDS_BASE}/xrpc/com.atproto.repo.createRecord",
            provider="publishing",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )
        response.raise_for_status()
        data = response.json()

        cid = data.get("cid", "")
        rkey = data.get("uri", "").split("/")[-1]
        handle = social_account.handle or self.did
        return PublishResult(
            status="succeeded",
            external_post_id=cid,
            external_post_url=f"https://bsky.app/profile/{handle}/post/{rkey}",
            payload={
                "cid": cid,
                "uri": data.get("uri", ""),
                "image_count": str(len(blob_refs)),
                "publish_attempt_key": publish_attempt_key,
            },
        )

    async def create_draft(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> DraftResult:
        text = self._select_text(assets)
        return DraftResult(
            status="draft_created",
            preview_text=text[:300],
            payload={"platform": self.platform, "image_count": str(len(self._media_assets(assets)))},
        )

    async def fetch_post_url(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
        provider_payload: dict[str, str] | None = None,
    ) -> str | None:
        provider_payload = provider_payload or {}
        uri = provider_payload.get("uri", "")
        if uri:
            rkey = uri.split("/")[-1]
            handle = social_account.handle or self.did
            return f"https://bsky.app/profile/{handle}/post/{rkey}"
        return None

    async def delete_or_unpublish_if_supported(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
    ) -> DeletionResult:
        if not external_post_id:
            return DeletionResult(status="noop", supported=True, payload={"reason": "missing_external_post_id"})
        if self.dry_run:
            return DeletionResult(status="deleted_dry_run", supported=True, payload={"external_post_id": external_post_id})
        return DeletionResult(status="manual_delete_required", supported=True, payload={"external_post_id": external_post_id})


