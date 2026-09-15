"""Account-scoped publish quotas, schedule TZ, and attribution snapshots (T4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.modules.publishing.models import SocialAccount


@dataclass(frozen=True)
class AccountQuotaDecision:
    allowed: bool
    retry_after_seconds: int
    key: str
    action: str


def account_quota_key(
    *,
    tenant_id: UUID,
    social_account_id: UUID,
    action: str,
) -> str:
    return f"rate_limit:account:{tenant_id}:{social_account_id}:{action}"


def account_publish_limit(account: SocialAccount | None) -> int:
    if account is not None:
        raw = (account.settings or {}).get("max_publishes_per_hour")
        try:
            if raw is not None:
                return max(1, int(str(raw)))
        except (TypeError, ValueError):
            pass
    return int(settings.PUBLISHING_ACCOUNT_MAX_PUBLISHES_PER_HOUR)


def account_retry_limit(account: SocialAccount | None) -> int:
    if account is not None:
        raw = (account.settings or {}).get("max_retries_per_hour")
        try:
            if raw is not None:
                return max(1, int(str(raw)))
        except (TypeError, ValueError):
            pass
    return int(settings.PUBLISHING_ACCOUNT_MAX_RETRIES_PER_HOUR)


async def consume_account_quota(
    *,
    tenant_id: UUID,
    social_account_id: UUID,
    action: str,
    max_attempts: int,
    window_seconds: int = 3600,
) -> AccountQuotaDecision:
    """
    Increment account-scoped Redis counter. Soft decision (no HTTPException) so
    workers can reschedule one account without blocking siblings.
    """
    key = account_quota_key(
        tenant_id=tenant_id, social_account_id=social_account_id, action=action
    )
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds)
    results = await pipe.execute()
    count = int(results[0])
    if count > max_attempts:
        ttl = await redis_client.ttl(key)
        return AccountQuotaDecision(
            allowed=False,
            retry_after_seconds=max(int(ttl or window_seconds), 1),
            key=key,
            action=action,
        )
    return AccountQuotaDecision(
        allowed=True,
        retry_after_seconds=0,
        key=key,
        action=action,
    )


async def consume_publish_quota(
    *,
    tenant_id: UUID,
    account: SocialAccount,
) -> AccountQuotaDecision:
    return await consume_account_quota(
        tenant_id=tenant_id,
        social_account_id=account.id,
        action="publish",
        max_attempts=account_publish_limit(account),
    )


async def consume_retry_quota(
    *,
    tenant_id: UUID,
    account: SocialAccount,
) -> AccountQuotaDecision:
    return await consume_account_quota(
        tenant_id=tenant_id,
        social_account_id=account.id,
        action="retry",
        max_attempts=account_retry_limit(account),
    )


def build_account_display_snapshot(account: SocialAccount) -> dict[str, str]:
    """Immutable attribution for posts/analytics after account delete/disconnect."""
    return {
        "social_account_id": str(account.id),
        "platform": str(account.platform),
        "display_name": account.display_name or "",
        "handle": account.handle or "",
        "account_external_id": account.account_external_id or "",
        "status": str(account.status),
        "auth_type": str(getattr(account, "auth_type", "") or ""),
    }


def account_label_from_snapshot(snapshot: dict[str, Any] | None, *, platform: str = "") -> str:
    if not snapshot:
        return platform or "unknown"
    handle = str(snapshot.get("handle") or "").strip()
    name = str(snapshot.get("display_name") or "").strip()
    plat = str(snapshot.get("platform") or platform or "").strip()
    identity = handle or name or str(snapshot.get("social_account_id") or "")[:8] or "account"
    return f"{plat} · {identity}" if plat else identity


def schedule_local_to_utc(
    when: datetime,
    *,
    tenant_timezone: str | None,
) -> datetime:
    """
    Persist schedules as UTC. Naive datetimes are interpreted in the tenant TZ
    (default UTC). Aware datetimes are converted to UTC.
    """
    if when.tzinfo is not None:
        return when.astimezone(timezone.utc)

    tz_name = (tenant_timezone or "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return when.replace(tzinfo=zone).astimezone(timezone.utc)
