from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

import httpx

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

_X_API_BASE = settings.X_API_BASE_URL.rstrip("/")
_X_UPLOAD_BASE = settings.X_UPLOAD_BASE_URL.rstrip("/")
_X_MAX_CHARS = 280
_MEDIA_ASSET_TYPES = {"image", "thumbnail"}


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
            dl = await request("GET", asset.public_url, provider="publishing")
            dl.raise_for_status()
            resp = await request(
                "POST",
                f"{_X_UPLOAD_BASE}/1.1/media/upload.json",
                provider="x",
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
        text: str,
        reply_to_id: str | None = None,
        media_ids: list[str] | None = None,
        *,
        publish_attempt_key: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> dict:
        _ = client  # legacy callers may still pass a client; policy request() owns I/O
        body: dict = {"text": text}
        if reply_to_id:
            body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if publish_attempt_key:
            # X API v2 supports Idempotency-Key for POST /2/tweets.
            headers["Idempotency-Key"] = publish_attempt_key[:128]
        response = await request(
            "POST",
            f"{_X_API_BASE}/2/tweets",
            provider="x",
            headers=headers,
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
            external_id = (
                f"dry-run-{sha256(publish_attempt_key.encode('utf-8')).hexdigest()[:24]}"
                if publish_attempt_key
                else f"dry-run-{uuid4()}"
            )
            return PublishResult(
                status="succeeded_dry_run",
                external_post_id=external_id,
                external_post_url=f"https://x.com/i/web/status/{external_id}",
                payload={"mode": "dry_run", "publish_attempt_key": publish_attempt_key},
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
        first_id: str | None = None
        last_id: str | None = None
        for i, text in enumerate(texts):
            # Attach media only to the first tweet in a thread
            tweet_media_ids = media_ids if i == 0 and media_ids else None
            data = await self._post_tweet(
                text,
                reply_to_id=last_id,
                media_ids=tweet_media_ids,
                publish_attempt_key=f"{publish_attempt_key}:{i}" if publish_attempt_key else "",
            )
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


