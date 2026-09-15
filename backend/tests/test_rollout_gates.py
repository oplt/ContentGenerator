"""T8.2 staged rollout gates."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from backend.core.rollout import (
    RolloutMode,
    apply_multi_account_gate,
    collapse_one_per_platform,
    decide_multi_account,
    evaluate_rollback,
    parse_rollout_mode,
    tenant_canary_bucket,
)


def _accounts(*platforms: str):
    return [SimpleNamespace(id=uuid4(), platform=platform, tenant_id=uuid4()) for platform in platforms]


def test_parse_rollout_mode_defaults_and_invalid() -> None:
    assert parse_rollout_mode("on") is RolloutMode.ON
    assert parse_rollout_mode("SHADOW") is RolloutMode.SHADOW
    assert parse_rollout_mode("nope") is RolloutMode.ON


def test_collapse_one_per_platform() -> None:
    tenant = uuid4()
    accounts = [
        SimpleNamespace(platform="x", tenant_id=tenant),
        SimpleNamespace(platform="x", tenant_id=tenant),
        SimpleNamespace(platform="linkedin", tenant_id=tenant),
    ]
    collapsed = collapse_one_per_platform(accounts)
    assert len(collapsed) == 2
    assert [a.platform for a in collapsed] == ["x", "linkedin"]


def test_off_collapses_multi_same_platform() -> None:
    tenant = uuid4()
    accounts = _accounts("x", "x", "linkedin")
    selected, decision = apply_multi_account_gate(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.OFF,
    )
    assert decision.multi_account_enabled is False
    assert len(selected) == 2


def test_on_keeps_multi() -> None:
    tenant = uuid4()
    accounts = _accounts("x", "x")
    selected, decision = apply_multi_account_gate(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.ON,
    )
    assert decision.multi_account_enabled is True
    assert len(selected) == 2


def test_shadow_serves_multi_and_marks_delta() -> None:
    tenant = uuid4()
    accounts = _accounts("x", "x")
    selected, decision = apply_multi_account_gate(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.SHADOW,
    )
    assert decision.shadow is True
    assert decision.selected_count == 2
    assert decision.collapsed_count == 1
    assert len(selected) == 2


def test_canary_allowlist_and_percent() -> None:
    tenant = uuid4()
    accounts = _accounts("x", "x")
    allowed, decision = apply_multi_account_gate(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.CANARY,
        canary_percent=0,
        allowlist=frozenset({str(tenant)}),
    )
    assert decision.reason == "canary_allowlist"
    assert len(allowed) == 2

    excluded, decision2 = apply_multi_account_gate(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.CANARY,
        canary_percent=0,
        allowlist=frozenset(),
    )
    assert decision2.reason == "canary_excluded"
    assert len(excluded) == 1

    bucket = tenant_canary_bucket(tenant)
    decision3 = decide_multi_account(
        accounts,
        tenant_id=tenant,
        mode=RolloutMode.CANARY,
        canary_percent=bucket + 1,
        allowlist=frozenset(),
    )
    assert decision3.multi_account_enabled is True
    assert decision3.reason == "canary_percent"


def test_evaluate_rollback_triggers_on_ambiguity_and_provider_failures() -> None:
    snapshot = {
        "counters": {
            "cg.publish.attempt.total": [
                {"attrs": {"outcome": "ambiguous", "platform": "x"}, "value": 6},
            ],
            "cg.publish.account_rate_limited.total": [
                {"attrs": {"platform": "x"}, "value": 2},
            ],
            "cg.provider.request.total": [
                {"attrs": {"outcome": "failure", "provider": "x"}, "value": 10},
                {"attrs": {"outcome": "success", "provider": "x"}, "value": 10},
            ],
        }
    }
    verdict = evaluate_rollback(
        snapshot,
        max_ambiguous_publish=5,
        max_rate_limited=50,
        max_provider_failure_ratio=0.4,
        min_provider_samples=10,
    )
    assert verdict.should_rollback is True
    assert any("publish_ambiguous" in reason for reason in verdict.reasons)
    assert any("provider_failure_ratio" in reason for reason in verdict.reasons)


def test_evaluate_rollback_clean_snapshot() -> None:
    verdict = evaluate_rollback({"counters": {}})
    assert verdict.should_rollback is False
    assert verdict.reasons == ()
