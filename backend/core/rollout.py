"""
Staged rollout gates for multi-account and related high-risk changes (T8.2).

Modes
-----
* ``off`` — collapse to one account per platform (legacy-safe).
* ``shadow`` — serve multi-account; record collapse delta for reconciliation.
* ``canary`` — multi-account only for allowlisted tenants or percentage bucket.
* ``on`` — full multi-account (default; matches shipped T4 behavior).

Rollback
--------
``evaluate_rollback`` inspects low-cardinality domain metric snapshots and
returns structured reasons when publish ambiguity, rate-limit storms, or
provider failure rates exceed configured thresholds.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import UUID

logger = logging.getLogger(__name__)


class RolloutMode(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    CANARY = "canary"
    ON = "on"


def parse_rollout_mode(raw: str | None) -> RolloutMode:
    value = (raw or RolloutMode.ON.value).strip().lower()
    try:
        return RolloutMode(value)
    except ValueError:
        logger.warning("rollout_mode_invalid value=%s falling_back=on", raw)
        return RolloutMode.ON


def parse_tenant_allowlist(raw: str) -> frozenset[str]:
    return frozenset(part.strip() for part in (raw or "").split(",") if part.strip())


def tenant_canary_bucket(tenant_id: UUID | str, *, salt: str = "multi-account") -> int:
    """Stable 0–99 bucket for percentage canaries (not a security boundary)."""
    digest = hashlib.sha256(f"{salt}:{tenant_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


@dataclass(frozen=True, slots=True)
class MultiAccountDecision:
    mode: RolloutMode
    multi_account_enabled: bool
    shadow: bool
    reason: str
    selected_count: int
    collapsed_count: int


@dataclass(frozen=True, slots=True)
class RollbackVerdict:
    should_rollback: bool
    reasons: tuple[str, ...]
    signals: dict[str, float]


def collapse_one_per_platform(accounts: Sequence[Any]) -> list[Any]:
    """Keep first account per platform (request order preserved)."""
    seen: set[str] = set()
    out: list[Any] = []
    for account in accounts:
        platform = str(getattr(account, "platform", "") or "unknown")
        if platform in seen:
            continue
        seen.add(platform)
        out.append(account)
    return out


def decide_multi_account(
    accounts: Sequence[Any],
    *,
    tenant_id: UUID | str,
    mode: RolloutMode,
    canary_percent: int,
    allowlist: frozenset[str],
) -> MultiAccountDecision:
    selected = list(accounts)
    collapsed = collapse_one_per_platform(selected)

    if mode is RolloutMode.ON:
        return MultiAccountDecision(
            mode=mode,
            multi_account_enabled=True,
            shadow=False,
            reason="rollout_on",
            selected_count=len(selected),
            collapsed_count=len(collapsed),
        )

    if mode is RolloutMode.OFF:
        return MultiAccountDecision(
            mode=mode,
            multi_account_enabled=False,
            shadow=False,
            reason="rollout_off",
            selected_count=len(collapsed),
            collapsed_count=len(collapsed),
        )

    if mode is RolloutMode.SHADOW:
        multi = len(selected) > len(collapsed)
        return MultiAccountDecision(
            mode=mode,
            multi_account_enabled=True,
            shadow=True,
            reason="shadow_compare" if multi else "shadow_single",
            selected_count=len(selected),
            collapsed_count=len(collapsed),
        )

    tenant_key = str(tenant_id)
    if tenant_key in allowlist:
        return MultiAccountDecision(
            mode=mode,
            multi_account_enabled=True,
            shadow=False,
            reason="canary_allowlist",
            selected_count=len(selected),
            collapsed_count=len(collapsed),
        )
    pct = max(0, min(100, int(canary_percent)))
    if tenant_canary_bucket(tenant_id) < pct:
        return MultiAccountDecision(
            mode=mode,
            multi_account_enabled=True,
            shadow=False,
            reason="canary_percent",
            selected_count=len(selected),
            collapsed_count=len(collapsed),
        )
    return MultiAccountDecision(
        mode=mode,
        multi_account_enabled=False,
        shadow=False,
        reason="canary_excluded",
        selected_count=len(collapsed),
        collapsed_count=len(collapsed),
    )


def apply_multi_account_gate(
    accounts: Sequence[Any],
    *,
    tenant_id: UUID | str,
    mode: RolloutMode,
    canary_percent: int = 0,
    allowlist: frozenset[str] | None = None,
) -> tuple[list[Any], MultiAccountDecision]:
    decision = decide_multi_account(
        accounts,
        tenant_id=tenant_id,
        mode=mode,
        canary_percent=canary_percent,
        allowlist=allowlist or frozenset(),
    )
    selected = list(accounts) if decision.multi_account_enabled else collapse_one_per_platform(accounts)

    if decision.shadow and decision.selected_count != decision.collapsed_count:
        logger.info(
            "multi_account_shadow tenant=%s selected=%s collapsed=%s delta=%s",
            tenant_id,
            decision.selected_count,
            decision.collapsed_count,
            decision.selected_count - decision.collapsed_count,
        )
        try:
            from backend.core.domain_metrics import domain_metrics

            domain_metrics.record_operation(
                "rollout.multi_account.shadow",
                outcome="delta" if decision.selected_count > decision.collapsed_count else "match",
                duration_ms=0.0,
            )
        except Exception:
            pass

    return selected, decision


def _counter_total(
    snapshot: Mapping[str, Any],
    metric: str,
    *,
    attr_pred: Mapping[str, str] | None = None,
) -> float:
    counters = snapshot.get("counters") or {}
    rows = counters.get(metric) or []
    total = 0.0
    for row in rows:
        attrs = row.get("attrs") or {}
        if attr_pred and any(attrs.get(key) != value for key, value in attr_pred.items()):
            continue
        total += float(row.get("value") or 0)
    return total


def evaluate_rollback(
    domain_snapshot: Mapping[str, Any],
    *,
    max_ambiguous_publish: float = 5.0,
    max_rate_limited: float = 50.0,
    max_provider_failure_ratio: float = 0.25,
    min_provider_samples: float = 20.0,
) -> RollbackVerdict:
    """
    Stateless gate using in-process /health/metrics domain snapshot.

    Thresholds are conservative defaults for canary windows; operators override
    via docs/rollout/gates.md playbook rather than hot-path config sprawl.
    """
    ambiguous = max(
        _counter_total(
            domain_snapshot,
            "cg.publish.attempt.total",
            attr_pred={"error_class": "ambiguous"},
        ),
        _counter_total(
            domain_snapshot,
            "cg.publish.attempt.total",
            attr_pred={"outcome": "ambiguous"},
        ),
    )

    rate_limited = _counter_total(domain_snapshot, "cg.publish.account_rate_limited.total")
    provider_fail = _counter_total(
        domain_snapshot, "cg.provider.request.total", attr_pred={"outcome": "failure"}
    ) + _counter_total(
        domain_snapshot, "cg.provider.request.total", attr_pred={"outcome": "transport_error"}
    )
    provider_ok = _counter_total(
        domain_snapshot, "cg.provider.request.total", attr_pred={"outcome": "success"}
    )
    provider_total = provider_fail + provider_ok
    failure_ratio = (provider_fail / provider_total) if provider_total >= min_provider_samples else 0.0

    reasons: list[str] = []
    if ambiguous >= max_ambiguous_publish:
        reasons.append(f"publish_ambiguous>={max_ambiguous_publish}")
    if rate_limited >= max_rate_limited:
        reasons.append(f"account_rate_limited>={max_rate_limited}")
    if provider_total >= min_provider_samples and failure_ratio >= max_provider_failure_ratio:
        reasons.append(f"provider_failure_ratio>={max_provider_failure_ratio}")

    return RollbackVerdict(
        should_rollback=bool(reasons),
        reasons=tuple(reasons),
        signals={
            "publish_ambiguous": ambiguous,
            "account_rate_limited": rate_limited,
            "provider_failure_ratio": round(failure_ratio, 4),
            "provider_samples": provider_total,
        },
    )


def rollout_status_dict(
    *,
    mode: RolloutMode,
    canary_percent: int,
    allowlist_count: int,
) -> dict[str, object]:
    return {
        "multi_account_mode": mode.value,
        "canary_percent": canary_percent,
        "allowlist_count": allowlist_count,
        "modes": [item.value for item in RolloutMode],
    }
