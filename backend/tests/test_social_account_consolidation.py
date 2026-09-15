"""Tests for SocialAccount / ConnectedAccount consolidation (T4.1)."""

from __future__ import annotations

from uuid import uuid4

from backend.modules.publishing.account_lineage import (
    ConsolidationActionKind,
    ConnectedSnapshot,
    JobSnapshot,
    SocialSnapshot,
    mint_legacy_external_id,
    plan_consolidation,
    resolve_external_id,
)


def test_mint_and_resolve_external_id() -> None:
    connected = uuid4()
    social = uuid4()
    assert mint_legacy_external_id(connected_id=connected) == f"legacy:connected:{connected}"
    assert resolve_external_id(provided="  abc  ", connected_id=connected) == "abc"
    assert resolve_external_id(provided=None, social_id=social) == f"legacy:social:{social}"


def test_orphan_connected_creates_social() -> None:
    tenant = uuid4()
    connected_id = uuid4()
    actions = plan_consolidation(
        connected=[
            ConnectedSnapshot(
                id=connected_id,
                tenant_id=tenant,
                platform="x",
                account_name="Main",
                social_account_id=None,
                status="active",
            )
        ],
        social=[],
    )
    kinds = [a.kind for a in actions]
    assert ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED in kinds
    create = next(a for a in actions if a.kind == ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED)
    assert create.external_id == f"legacy:connected:{connected_id}"
    assert create.connected_id == connected_id


def test_linked_connected_is_noop_for_create() -> None:
    tenant = uuid4()
    social_id = uuid4()
    connected_id = uuid4()
    actions = plan_consolidation(
        connected=[
            ConnectedSnapshot(
                id=connected_id,
                tenant_id=tenant,
                platform="x",
                account_name="Main",
                social_account_id=social_id,
                status="active",
            )
        ],
        social=[
            SocialSnapshot(
                id=social_id,
                tenant_id=tenant,
                platform="x",
                display_name="Main",
                account_external_id="ext-1",
                status="connected",
            )
        ],
    )
    assert ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED not in [a.kind for a in actions]
    assert ConsolidationActionKind.MINT_EXTERNAL_ID not in [a.kind for a in actions]


def test_null_external_id_gets_minted() -> None:
    tenant = uuid4()
    social_id = uuid4()
    actions = plan_consolidation(
        connected=[],
        social=[
            SocialSnapshot(
                id=social_id,
                tenant_id=tenant,
                platform="instagram",
                display_name="IG",
                account_external_id=None,
                status="connected",
            )
        ],
    )
    mint = next(a for a in actions if a.kind == ConsolidationActionKind.MINT_EXTERNAL_ID)
    assert mint.social_id == social_id
    assert mint.external_id == f"legacy:social:{social_id}"


def test_duplicate_connected_names_quarantined() -> None:
    tenant = uuid4()
    first = uuid4()
    second = uuid4()
    social_id = uuid4()
    actions = plan_consolidation(
        connected=[
            ConnectedSnapshot(
                id=first,
                tenant_id=tenant,
                platform="x",
                account_name="Dup",
                social_account_id=social_id,
                status="active",
            ),
            ConnectedSnapshot(
                id=second,
                tenant_id=tenant,
                platform="x",
                account_name="dup",
                social_account_id=None,
                status="active",
            ),
        ],
        social=[
            SocialSnapshot(
                id=social_id,
                tenant_id=tenant,
                platform="x",
                display_name="Dup",
                account_external_id="ext",
                status="connected",
            )
        ],
    )
    quarantines = [a for a in actions if a.kind == ConsolidationActionKind.QUARANTINE_CONNECTED]
    assert len(quarantines) == 1
    assert quarantines[0].connected_id == second
    assert quarantines[0].reason == "duplicate_platform_account_name"


def test_job_inherits_social_from_connected() -> None:
    tenant = uuid4()
    social_id = uuid4()
    connected_id = uuid4()
    job_id = uuid4()
    actions = plan_consolidation(
        connected=[
            ConnectedSnapshot(
                id=connected_id,
                tenant_id=tenant,
                platform="x",
                account_name="Main",
                social_account_id=social_id,
                status="active",
            )
        ],
        social=[
            SocialSnapshot(
                id=social_id,
                tenant_id=tenant,
                platform="x",
                display_name="Main",
                account_external_id="ext",
                status="connected",
            )
        ],
        jobs=[
            JobSnapshot(
                id=job_id,
                tenant_id=tenant,
                platform="x",
                social_account_id=None,
                connected_account_id=connected_id,
            )
        ],
    )
    backfills = [a for a in actions if a.kind == ConsolidationActionKind.BACKFILL_JOB_SOCIAL_ID]
    assert len(backfills) == 1
    assert backfills[0].social_id == social_id
    assert backfills[0].job_id == job_id


def test_cross_tenant_rows_do_not_merge() -> None:
    t1, t2 = uuid4(), uuid4()
    c1, c2 = uuid4(), uuid4()
    actions = plan_consolidation(
        connected=[
            ConnectedSnapshot(
                id=c1, tenant_id=t1, platform="x", account_name="A", social_account_id=None, status="active"
            ),
            ConnectedSnapshot(
                id=c2, tenant_id=t2, platform="x", account_name="A", social_account_id=None, status="active"
            ),
        ],
        social=[],
    )
    creates = [a for a in actions if a.kind == ConsolidationActionKind.CREATE_SOCIAL_FROM_CONNECTED]
    assert len(creates) == 2
    assert {a.tenant_id for a in creates} == {t1, t2}
