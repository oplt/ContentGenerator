"""Publishing provider facade — stable import surface."""

from __future__ import annotations

from backend.core.config import settings
from backend.modules.publishing.bluesky_provider import BlueskyPublishingProvider
from backend.modules.publishing.provider_base import (
    AuthValidationResult,
    DeletionResult,
    DraftResult,
    ManualFallbackProvider,
    PublishResult,
    PublishingProvider,
    SchedulingResult,
    StubPublishingProvider,
)
from backend.modules.publishing.x_provider import XPublishingProvider


def _stub_or_manual(platform: str, *, prefer_stub: bool) -> PublishingProvider:
    if prefer_stub:
        return StubPublishingProvider(platform)
    return ManualFallbackProvider(platform)


def _try_real_provider(
    platform: str,
    *,
    access_token: str,
    account_external_id: str,
    dry_run: bool,
) -> PublishingProvider | None:
    if platform == "x" and access_token:
        return XPublishingProvider(access_token=access_token, dry_run=dry_run)
    if platform == "bluesky" and access_token and account_external_id:
        return BlueskyPublishingProvider(
            access_token=access_token,
            did=account_external_id,
            dry_run=dry_run,
        )
    return None


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
      1. Real token → platform provider (x / bluesky)
      2. Dry-run / stub → StubPublishingProvider
      3. Otherwise → ManualFallbackProvider
    """
    is_dry_run = dry_run or (use_stub and not access_token)
    prefer_stub = is_dry_run or settings.SOCIAL_DRY_RUN_BY_DEFAULT
    real = _try_real_provider(
        platform,
        access_token=access_token,
        account_external_id=account_external_id,
        dry_run=is_dry_run,
    )
    if real is not None:
        return real
    # Missing credentials: x/bluesky honor explicit dry-run only; others also
    # follow SOCIAL_DRY_RUN_BY_DEFAULT.
    stub_flag = is_dry_run if platform in {"x", "bluesky"} else prefer_stub
    return _stub_or_manual(platform, prefer_stub=stub_flag)


__all__ = [
    "AuthValidationResult",
    "BlueskyPublishingProvider",
    "DeletionResult",
    "DraftResult",
    "ManualFallbackProvider",
    "PublishResult",
    "PublishingProvider",
    "SchedulingResult",
    "StubPublishingProvider",
    "XPublishingProvider",
    "get_provider",
]
