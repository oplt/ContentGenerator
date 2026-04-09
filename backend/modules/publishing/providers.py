from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from backend.core.config import settings
from backend.modules.content_generation.models import GeneratedAsset
from backend.modules.publishing.models import SocialAccount

# X API v2 base URL (overridable for tests)
_X_API_BASE = settings.X_API_BASE_URL.rstrip("/")
# X media upload base URL (v1.1, different from the main API)
_X_UPLOAD_BASE = settings.X_UPLOAD_BASE_URL.rstrip("/")
# Bluesky PDS URL (overridable for tests)
_BSKY_PDS_BASE = settings.BLUESKY_PDS_URL.rstrip("/")

# X post character limit
_X_MAX_CHARS = 280

# Asset types treated as uploadable media
_MEDIA_ASSET_TYPES = {"image", "thumbnail"}


@dataclass
class PublishResult:
    status: str
    external_post_id: str | None
    external_post_url: str | None
    payload: dict[str, str]
    manual_required: bool = False


@dataclass
class AuthValidationResult:
    is_valid: bool
    account_status: str
    detail: str | None = None


@dataclass
class DraftResult:
    status: str
    preview_text: str
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class SchedulingResult:
    status: str
    scheduled_for: datetime | None
    native_supported: bool
    payload: dict[str, str] = field(default_factory=dict)


@dataclass
class DeletionResult:
    status: str
    supported: bool
    payload: dict[str, str] = field(default_factory=dict)


class PublishingProvider:
    platform: str = "generic"

    def capabilities(self) -> dict[str, str]:
        raise NotImplementedError

    async def validate_auth(self, *, social_account: SocialAccount) -> AuthValidationResult:
        return AuthValidationResult(is_valid=True, account_status="connected")

    async def create_draft(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> DraftResult:
        preview_text = ""
        for asset in assets:
            if asset.asset_type == "text_variant" and asset.text_content:
                preview_text = asset.text_content.strip()
                break
        return DraftResult(
            status="draft_created",
            preview_text=preview_text[:300],
            payload={"asset_count": str(len(assets))},
        )

    async def publish_now(
        self,
        *,
        social_account: SocialAccount,
        assets: list[GeneratedAsset],
        publish_attempt_key: str = "",
    ) -> PublishResult:
        return await self.publish(social_account=social_account, assets=assets)

    async def schedule_publish(
        self,
        *,
        social_account: SocialAccount,
        assets: list[GeneratedAsset],
        scheduled_for: datetime,
    ) -> SchedulingResult:
        return SchedulingResult(
            status="scheduled_application_fallback",
            scheduled_for=scheduled_for,
            native_supported=False,
            payload={"mode": "application_fallback", "asset_count": str(len(assets))},
        )

    async def fetch_post_url(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
        provider_payload: dict[str, str] | None = None,
    ) -> str | None:
        return None

    async def fetch_post_metrics(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
        provider_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        return dict(provider_payload or {})

    async def delete_or_unpublish_if_supported(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
    ) -> DeletionResult:
        return DeletionResult(
            status="not_supported",
            supported=False,
            payload={"reason": "delete_not_supported"},
        )

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        raise NotImplementedError


class StubPublishingProvider(PublishingProvider):
    def __init__(self, platform: str):
        self.platform = platform

    def capabilities(self) -> dict[str, str]:
        return {"text": "true", "video": "true", "mode": "stub", "native_scheduling": "false"}

    async def validate_auth(self, *, social_account: SocialAccount) -> AuthValidationResult:
        return AuthValidationResult(is_valid=True, account_status="connected", detail="stub_provider")

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        external_id = str(uuid4())
        return PublishResult(
            status="succeeded",
            external_post_id=external_id,
            external_post_url=f"https://example.invalid/{self.platform}/{external_id}",
            payload={"mode": "stub", "asset_count": str(len(assets))},
        )


class ManualFallbackProvider(PublishingProvider):
    def __init__(self, platform: str):
        self.platform = platform

    def capabilities(self) -> dict[str, str]:
        return {"text": "limited", "video": "limited", "mode": "manual", "native_scheduling": "false"}

    async def validate_auth(self, *, social_account: SocialAccount) -> AuthValidationResult:
        return AuthValidationResult(
            is_valid=False,
            account_status="needs_reauth",
            detail="Provider credentials or API capability unavailable",
        )

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        return PublishResult(
            status="manual_required",
            external_post_id=None,
            external_post_url=None,
            payload={"reason": "Provider credentials or API capability unavailable"},
            manual_required=True,
        )


class XPublishingProvider(PublishingProvider):
    """
    Publishes to X (Twitter) using API v2 with OAuth 2.0 Bearer token.
    Supports single posts and threads (multiple assets → reply chain).
    """
    platform = "x"

    def __init__(self, access_token: str, dry_run: bool = False):
        self.access_token = access_token
        self.dry_run = dry_run
        self._upload_cache: dict[str, str] = {}

    def capabilities(self) -> dict[str, str]:
        return {
            "text": "true",
            "video": "false",
            "thread": "true",
            "mode": "x_api_v2",
            "native_scheduling": "false",
            "delete": "true",
        }

    async def validate_auth(self, *, social_account: SocialAccount) -> AuthValidationResult:
        return AuthValidationResult(
            is_valid=bool(self.access_token),
            account_status="connected" if self.access_token else "needs_reauth",
            detail="bearer_token_present" if self.access_token else "missing_access_token",
        )

    def _select_text(self, assets: list[GeneratedAsset]) -> list[str]:
        """Return text snippets for X from text_variant assets, split at 280 chars."""
        texts: list[str] = []
        for asset in assets:
            if asset.asset_type == "text_variant" and asset.text_content:
                content = asset.text_content.strip()
                # Split into 280-char chunks for threading
                while len(content) > _X_MAX_CHARS:
                    split_at = content.rfind(" ", 0, _X_MAX_CHARS - 3)
                    if split_at == -1:
                        split_at = _X_MAX_CHARS - 3
                    texts.append(content[:split_at] + "…")
                    content = content[split_at:].strip()
                if content:
                    texts.append(content)
        return texts or [""]

    def _media_assets(self, assets: list[GeneratedAsset]) -> list[GeneratedAsset]:
        """Return image/thumbnail assets that have a downloadable URL."""
        return [
            a for a in assets
            if a.asset_type in _MEDIA_ASSET_TYPES
            and a.public_url
        ]

    async def _upload_media_id(self, asset: GeneratedAsset, publish_attempt_key: str = "") -> str | None:
        """
        Download asset bytes and upload to X media upload API.
        Returns media_id_string on success, None on failure (best-effort).
        """
        if not asset.public_url:
            return None
        cache_key = f"{publish_attempt_key}:{asset.checksum or asset.public_url or asset.id}"
        if publish_attempt_key and cache_key in self._upload_cache:
            return self._upload_cache[cache_key]
        try:
            async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
                dl = await client.get(asset.public_url)
                dl.raise_for_status()
                resp = await client.post(
                    f"{_X_UPLOAD_BASE}/1.1/media/upload.json",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    files={"media": ("media", dl.content, asset.mime_type or "application/octet-stream")},
                )
                resp.raise_for_status()
                media_id = resp.json().get("media_id_string")
                if media_id and publish_attempt_key:
                    self._upload_cache[cache_key] = media_id
                return media_id
        except Exception:
            return None

    async def _post_tweet(
        self,
        client: httpx.AsyncClient,
        text: str,
        reply_to_id: str | None = None,
        media_ids: list[str] | None = None,
    ) -> dict:
        body: dict = {"text": text}
        if reply_to_id:
            body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        response = await client.post(
            f"{_X_API_BASE}/2/tweets",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        return response.json()

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
            external_id = f"dry-run-{uuid4()}"
            return PublishResult(
                status="succeeded_dry_run",
                external_post_id=external_id,
                external_post_url=f"https://x.com/i/web/status/{external_id}",
                payload={"mode": "dry_run"},
            )

        # Upload media assets (best-effort — failure does not abort the post)
        media_ids: list[str] = []
        for asset in self._media_assets(assets):
            try:
                media_id = await self._upload_media_id(asset, publish_attempt_key=publish_attempt_key)
            except Exception:
                media_id = None
            if media_id:
                media_ids.append(media_id)

        texts = self._select_text(assets)
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            first_id: str | None = None
            last_id: str | None = None
            for i, text in enumerate(texts):
                # Attach media only to the first tweet in a thread
                tweet_media_ids = media_ids if i == 0 and media_ids else None
                data = await self._post_tweet(client, text, reply_to_id=last_id, media_ids=tweet_media_ids)
                tweet_id = data.get("data", {}).get("id")
                if first_id is None:
                    first_id = tweet_id
                last_id = tweet_id

        handle = social_account.handle or social_account.account_external_id or "user"
        return PublishResult(
            status="succeeded",
            external_post_id=first_id,
            external_post_url=f"https://x.com/{handle}/status/{first_id}" if first_id else None,
            payload={
                "tweet_count": str(len(texts)),
                "first_tweet_id": first_id or "",
                "media_count": str(len(media_ids)),
                "publish_attempt_key": publish_attempt_key,
            },
        )

    async def create_draft(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> DraftResult:
        texts = self._select_text(assets)
        return DraftResult(
            status="draft_created",
            preview_text=(texts[0] if texts else "")[:280],
            payload={"tweet_count": str(len(texts)), "platform": self.platform},
        )

    async def fetch_post_url(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
        provider_payload: dict[str, str] | None = None,
    ) -> str | None:
        if not external_post_id:
            return None
        handle = social_account.handle or social_account.account_external_id or "user"
        return f"https://x.com/{handle}/status/{external_post_id}"

    async def fetch_post_metrics(
        self,
        *,
        social_account: SocialAccount,
        external_post_id: str | None,
        provider_payload: dict[str, str] | None = None,
    ) -> dict[str, str]:
        payload = dict(provider_payload or {})
        if external_post_id:
            payload.setdefault("external_post_id", external_post_id)
        payload.setdefault("platform", self.platform)
        return payload

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

    async def _upload_blob(self, client: httpx.AsyncClient, asset: GeneratedAsset) -> dict | None:
        """
        Download asset bytes and upload as an AT Protocol blob.
        Returns the blob ref dict on success, None on failure (best-effort).
        """
        if not asset.public_url:
            return None
        try:
            dl = await client.get(asset.public_url)
            dl.raise_for_status()
            resp = await client.post(
                f"{_BSKY_PDS_BASE}/xrpc/com.atproto.repo.uploadBlob",
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

        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            # Upload image blobs and attach as embed (best-effort)
            blob_refs: list[dict] = []
            for asset in self._media_assets(assets):
                blob = await self._upload_blob(client, asset)
                if blob:
                    blob_refs.append({"alt": "", "image": blob})

            if blob_refs:
                record["embed"] = {
                    "$type": "app.bsky.embed.images",
                    "images": blob_refs,
                }

            response = await client.post(
                f"{_BSKY_PDS_BASE}/xrpc/com.atproto.repo.createRecord",
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


def get_provider(
    platform: str,
    *,
    use_stub: bool,
    access_token: str = "",
    account_external_id: str = "",
    dry_run: bool = False,
) -> PublishingProvider:
    """
    Factory for publishing providers.

    Resolution order:
      1. If use_stub or SOCIAL_DRY_RUN_BY_DEFAULT and no real token → StubPublishingProvider
      2. If platform == "x" and access_token → XPublishingProvider
      3. If platform == "bluesky" and access_token + account_external_id → BlueskyPublishingProvider
      4. Otherwise → ManualFallbackProvider
    """
    is_dry_run = dry_run or (use_stub and not access_token)

    if platform == "x":
        if access_token:
            return XPublishingProvider(access_token=access_token, dry_run=is_dry_run)
        if is_dry_run:
            return StubPublishingProvider(platform)
        return ManualFallbackProvider(platform)

    if platform == "bluesky":
        if access_token and account_external_id:
            return BlueskyPublishingProvider(
                access_token=access_token,
                did=account_external_id,
                dry_run=is_dry_run,
            )
        if is_dry_run:
            return StubPublishingProvider(platform)
        return ManualFallbackProvider(platform)

    supported_stub_platforms = {"telegram", "instagram", "threads", "tiktok", "youtube"}
    if platform in supported_stub_platforms:
        if is_dry_run or settings.SOCIAL_DRY_RUN_BY_DEFAULT:
            return StubPublishingProvider(platform)
        return ManualFallbackProvider(platform)

    # All other platforms use stub for now
    if is_dry_run or settings.SOCIAL_DRY_RUN_BY_DEFAULT:
        return StubPublishingProvider(platform)
    return ManualFallbackProvider(platform)
