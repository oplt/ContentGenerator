"""Tests for account-scoped quotas, schedules, and attribution (T4.4)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from backend.modules.publishing.account_ops import (
    account_label_from_snapshot,
    account_publish_limit,
    account_quota_key,
    build_account_display_snapshot,
    schedule_local_to_utc,
)


def test_quota_keys_are_per_account() -> None:
    tenant = uuid4()
    a = uuid4()
    b = uuid4()
    assert account_quota_key(tenant_id=tenant, social_account_id=a, action="publish") != account_quota_key(
        tenant_id=tenant, social_account_id=b, action="publish"
    )


def test_account_settings_override_publish_limit() -> None:
    account = SimpleNamespace(settings={"max_publishes_per_hour": "2"})
    assert account_publish_limit(account) == 2  # type: ignore[arg-type]
    assert account_publish_limit(SimpleNamespace(settings={})) >= 1  # type: ignore[arg-type]


def test_schedule_naive_local_converts_to_utc() -> None:
    local = datetime(2026, 6, 15, 12, 0, 0)  # noon in US/Eastern → 16:00 UTC (EDT)
    utc = schedule_local_to_utc(local, tenant_timezone="America/New_York")
    assert utc.tzinfo is not None
    assert utc.hour == 16


def test_schedule_aware_preserves_instant() -> None:
    aware = datetime(2026, 1, 1, 0, 0, tzinfo=__import__("datetime").timezone.utc)
    assert schedule_local_to_utc(aware, tenant_timezone="Europe/Berlin") == aware


def test_display_snapshot_survives_for_deleted_account_label() -> None:
    account = SimpleNamespace(
        id=uuid4(),
        platform="x",
        display_name="Brand X",
        handle="@brandx",
        account_external_id="ext",
        status="disconnected",
        auth_type="oauth",
    )
    snap = build_account_display_snapshot(account)  # type: ignore[arg-type]
    label = account_label_from_snapshot(snap)
    assert "x" in label
    assert "@brandx" in label
    # Label still works without live SocialAccount row.
    assert account_label_from_snapshot(snap, platform="x") == "x · @brandx"
