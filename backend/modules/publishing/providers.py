from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from backend.core.config import settings
from backend.modules.content_generation.models import GeneratedAsset
from backend.modules.publishing.models import SocialAccount


@dataclass
class PublishResult:
    status: str
    external_post_id: str | None
    external_post_url: str | None
    payload: dict[str, str]
    manual_required: bool = False


class PublishingProvider:
    platform: str = "generic"

    def capabilities(self) -> dict[str, str]:
        raise NotImplementedError

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        raise NotImplementedError


class StubPublishingProvider(PublishingProvider):
    def __init__(self, platform: str):
        self.platform = platform

    def capabilities(self) -> dict[str, str]:
        return {"text": "true", "video": "true", "mode": "stub"}

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
        return {"text": "limited", "video": "limited", "mode": "manual"}

    async def publish(self, *, social_account: SocialAccount, assets: list[GeneratedAsset]) -> PublishResult:
        return PublishResult(
            status="manual_required",
            external_post_id=None,
            external_post_url=None,
            payload={"reason": "Provider credentials or API capability unavailable"},
            manual_required=True,
        )


def get_provider(platform: str, *, use_stub: bool) -> PublishingProvider:
    if use_stub or settings.SOCIAL_DRY_RUN_BY_DEFAULT:
        return StubPublishingProvider(platform)
    return ManualFallbackProvider(platform)
