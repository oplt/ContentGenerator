"""Resolve tenant-authorized social accounts for generation and publishing (T4.2)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from typing import Protocol

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.rollout import (
    apply_multi_account_gate,
    parse_rollout_mode,
    parse_tenant_allowlist,
)
from backend.modules.publishing.models import SocialAccount, SocialAccountStatus


class _SocialAccountLookup(Protocol):
    async def get_social_accounts_by_ids(
        self, tenant_id: UUID, account_ids: list[UUID]
    ) -> list[SocialAccount]: ...

    async def get_social_account_by_platform(
        self, tenant_id: UUID, platform: str
    ) -> SocialAccount | None: ...


@dataclass(frozen=True)
class AccountTarget:
    account: SocialAccount
    variant_fingerprint: str


def variant_fingerprint(account: SocialAccount) -> str:
    """
    Equivalent accounts share one generated platform variant.

    Fingerprint = platform + capability_flags + settings (stable JSON).
    """
    payload = {
        "platform": account.platform,
        "capability_flags": account.capability_flags or {},
        "settings": account.settings or {},
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"{account.platform}:{digest}"


def build_publish_idempotency_key(
    *,
    content_job_id: UUID,
    social_account_id: UUID,
    scheduled_for: datetime | None,
    dry_run: bool,
    intent: str = "publish",
    client_key: str | None = None,
    content_variant_id: UUID | None = None,
) -> str:
    """One account + one logical variant + one publishing intent → deterministic key."""
    if client_key:
        if content_variant_id is not None:
            return f"{client_key}:{social_account_id}:{content_variant_id}"
        return f"{client_key}:{social_account_id}"
    schedule_token = scheduled_for.isoformat() if scheduled_for else "immediate"
    mode = "dry" if dry_run else "live"
    parts = [str(content_job_id), str(social_account_id)]
    if content_variant_id is not None:
        parts.append(str(content_variant_id))
    parts.extend([schedule_token, intent, mode])
    return ":".join(parts)


def unique_platforms(accounts: list[SocialAccount]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for account in accounts:
        if account.platform not in seen:
            seen.add(account.platform)
            ordered.append(account.platform)
    return ordered


def group_by_fingerprint(accounts: list[SocialAccount]) -> dict[str, list[SocialAccount]]:
    groups: dict[str, list[SocialAccount]] = {}
    for account in accounts:
        fp = variant_fingerprint(account)
        groups.setdefault(fp, []).append(account)
    return groups


def assert_accounts_authorized(
    *,
    tenant_id: UUID,
    requested_ids: list[UUID],
    found: list[SocialAccount],
) -> None:
    found_ids = {account.id for account in found}
    missing = [str(account_id) for account_id in requested_ids if account_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized or unknown social_account_ids: {', '.join(missing)}",
        )
    quarantined = [
        str(account.id)
        for account in found
        if account.status == SocialAccountStatus.QUARANTINED.value
    ]
    if quarantined:
        raise HTTPException(
            status_code=400,
            detail=f"Quarantined social_account_ids cannot be selected: {', '.join(quarantined)}",
        )
    # Defense in depth — repo filters by tenant, but enforce here too.
    foreign = [str(account.id) for account in found if account.tenant_id != tenant_id]
    if foreign:
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized or unknown social_account_ids: {', '.join(foreign)}",
        )


def parse_stored_account_ids(raw: list[str] | None) -> list[UUID]:
    ids: list[UUID] = []
    for item in raw or []:
        try:
            ids.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return ids


async def resolve_social_accounts(
    *,
    repo: _SocialAccountLookup,
    tenant_id: UUID,
    social_account_ids: list[UUID] | None = None,
    platforms: list[str] | None = None,
    stored_account_ids: list[str] | None = None,
) -> list[SocialAccount]:
    """
    Resolve publish/generate targets.

    Precedence: explicit ``social_account_ids`` → stored job/plan IDs → legacy
    platform-only lookup (one account per platform, oldest non-quarantined).
    """
    if social_account_ids:
        found = await repo.get_social_accounts_by_ids(tenant_id, social_account_ids)
        assert_accounts_authorized(
            tenant_id=tenant_id, requested_ids=social_account_ids, found=found
        )
        # Preserve request order.
        by_id = {account.id: account for account in found}
        return _gated_accounts(
            tenant_id,
            [by_id[account_id] for account_id in social_account_ids if account_id in by_id],
        )

    stored = parse_stored_account_ids(stored_account_ids)
    if stored:
        found = await repo.get_social_accounts_by_ids(tenant_id, stored)
        assert_accounts_authorized(tenant_id=tenant_id, requested_ids=stored, found=found)
        by_id = {account.id: account for account in found}
        return _gated_accounts(
            tenant_id,
            [by_id[account_id] for account_id in stored if account_id in by_id],
        )

    if platforms:
        accounts: list[SocialAccount] = []
        for platform in platforms:
            account = await repo.get_social_account_by_platform(tenant_id, platform)
            if account is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"No social account configured for {platform}",
                )
            accounts.append(account)
        return _gated_accounts(tenant_id, accounts)

    return []


def _gated_accounts(tenant_id: UUID, accounts: list[SocialAccount]) -> list[SocialAccount]:
    selected, _decision = apply_multi_account_gate(
        accounts,
        tenant_id=tenant_id,
        mode=parse_rollout_mode(settings.MULTI_ACCOUNT_ROLLOUT_MODE),
        canary_percent=settings.MULTI_ACCOUNT_CANARY_PERCENT,
        allowlist=parse_tenant_allowlist(settings.MULTI_ACCOUNT_CANARY_TENANT_IDS),
    )
    return selected


def to_targets(accounts: list[SocialAccount]) -> list[AccountTarget]:
    return [
        AccountTarget(account=account, variant_fingerprint=variant_fingerprint(account))
        for account in accounts
    ]
