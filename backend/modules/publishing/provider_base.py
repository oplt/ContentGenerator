from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from uuid import uuid4

from backend.modules.content_generation.models import GeneratedAsset
from backend.modules.publishing.models import SocialAccount


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
        return await self.publish_now(social_account=social_account, assets=assets)

    async def publish_now(
        self,
        *,
        social_account: SocialAccount,
        assets: list[GeneratedAsset],
        publish_attempt_key: str = "",
    ) -> PublishResult:
        # Deterministic ID so retries with the same attempt key do not invent a new post.
        if publish_attempt_key:
            external_id = sha256(publish_attempt_key.encode("utf-8")).hexdigest()[:32]
        else:
            external_id = str(uuid4())
        return PublishResult(
            status="succeeded",
            external_post_id=external_id,
            external_post_url=f"https://example.invalid/{self.platform}/{external_id}",
            payload={
                "mode": "stub",
                "asset_count": str(len(assets)),
                "publish_attempt_key": publish_attempt_key,
            },
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


