"""Tests for account selection through generate/publish (T4.2)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.modules.publishing.account_selection import (
    assert_accounts_authorized,
    build_publish_idempotency_key,
    group_by_fingerprint,
    unique_platforms,
    variant_fingerprint,
)
from backend.modules.publishing.models import SocialAccountStatus


def _account(
    *,
    tenant_id=None,
    platform="x",
    caps=None,
    settings=None,
    status=SocialAccountStatus.CONNECTED.value,
):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        platform=platform,
        capability_flags=caps or {},
        settings=settings or {},
        status=status,
    )


def test_variant_fingerprint_equal_for_equivalent_accounts() -> None:
    tenant = uuid4()
    a = _account(tenant_id=tenant, platform="x", caps={"draft": "1"}, settings={"tone": "a"})
    b = _account(tenant_id=tenant, platform="x", caps={"draft": "1"}, settings={"tone": "a"})
    assert variant_fingerprint(a) == variant_fingerprint(b)  # type: ignore[arg-type]
    assert variant_fingerprint(a).startswith("x:")  # type: ignore[arg-type]


def test_variant_fingerprint_differs_when_settings_differ() -> None:
    tenant = uuid4()
    a = _account(tenant_id=tenant, platform="x", settings={"tone": "a"})
    b = _account(tenant_id=tenant, platform="x", settings={"tone": "b"})
    assert variant_fingerprint(a) != variant_fingerprint(b)  # type: ignore[arg-type]


def test_group_by_fingerprint_collapses_same_platform_policy() -> None:
    tenant = uuid4()
    a = _account(tenant_id=tenant, platform="x")
    b = _account(tenant_id=tenant, platform="x")
    c = _account(tenant_id=tenant, platform="instagram")
    groups = group_by_fingerprint([a, b, c])  # type: ignore[list-item]
    assert len(groups) == 2
    x_group = next(v for k, v in groups.items() if k.startswith("x:"))
    assert len(x_group) == 2


def test_unique_platforms_preserves_order() -> None:
    tenant = uuid4()
    accounts = [
        _account(tenant_id=tenant, platform="instagram"),
        _account(tenant_id=tenant, platform="x"),
        _account(tenant_id=tenant, platform="instagram"),
    ]
    assert unique_platforms(accounts) == ["instagram", "x"]  # type: ignore[arg-type]


def test_idempotency_includes_account_and_schedule() -> None:
    job_id = uuid4()
    account_id = uuid4()
    key = build_publish_idempotency_key(
        content_job_id=job_id,
        social_account_id=account_id,
        scheduled_for=None,
        dry_run=True,
    )
    assert str(account_id) in key
    assert str(job_id) in key
    other = build_publish_idempotency_key(
        content_job_id=job_id,
        social_account_id=uuid4(),
        scheduled_for=None,
        dry_run=True,
    )
    assert key != other


def test_client_idempotency_key_suffixes_account() -> None:
    account_id = uuid4()
    key = build_publish_idempotency_key(
        content_job_id=uuid4(),
        social_account_id=account_id,
        scheduled_for=None,
        dry_run=False,
        client_key="client-batch-1",
    )
    assert key == f"client-batch-1:{account_id}"


def test_unauthorized_account_ids_rejected() -> None:
    tenant = uuid4()
    requested = [uuid4(), uuid4()]
    found = [_account(tenant_id=tenant)]
    found[0].id = requested[0]
    with pytest.raises(HTTPException) as exc:
        assert_accounts_authorized(
            tenant_id=tenant,
            requested_ids=requested,
            found=found,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 403


def test_quarantined_account_rejected() -> None:
    tenant = uuid4()
    account_id = uuid4()
    found = [_account(tenant_id=tenant, status=SocialAccountStatus.QUARANTINED.value)]
    found[0].id = account_id
    with pytest.raises(HTTPException) as exc:
        assert_accounts_authorized(
            tenant_id=tenant,
            requested_ids=[account_id],
            found=found,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 400


def test_two_same_platform_accounts_need_two_idempotency_keys() -> None:
    """Mixed multi-account publish must not collapse to platform-only keys."""
    job_id = uuid4()
    a = uuid4()
    b = uuid4()
    key_a = build_publish_idempotency_key(
        content_job_id=job_id, social_account_id=a, scheduled_for=None, dry_run=True
    )
    key_b = build_publish_idempotency_key(
        content_job_id=job_id, social_account_id=b, scheduled_for=None, dry_run=True
    )
    assert key_a != key_b
    assert f"{job_id}:x" not in {key_a, key_b}
