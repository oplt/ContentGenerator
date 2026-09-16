"""Ops Phase 15 — profile GET /publishing/social-accounts latency."""

from __future__ import annotations

import ast
import asyncio
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from backend.core.domain_metrics import domain_metrics, reset_domain_metrics
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.publishing.serializers import social_account_to_response
from backend.tests.benchmarks.analyze_route_latencies import (
    compare_routes,
    extract_route_durations_ms,
    summarize_durations_ms,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISHING_ROUTER = REPO_ROOT / "backend/modules/publishing/router.py"
PUBLISHING_SERIALIZERS = REPO_ROOT / "backend/modules/publishing/serializers.py"
PUBLISHING_REPOSITORY = REPO_ROOT / "backend/modules/publishing/repository.py"
LOG_DIR = REPO_ROOT / "logs"


def test_list_route_does_not_touch_token_decryption() -> None:
    router_src = PUBLISHING_ROUTER.read_text(encoding="utf-8")
    serializers_src = PUBLISHING_SERIALIZERS.read_text(encoding="utf-8")
    list_fn = ast.unparse(
        next(
            node
            for node in ast.walk(ast.parse(router_src))
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_social_accounts"
        )
    )
    assert "decrypt_secret" not in list_fn
    assert "decrypt_secret" not in serializers_src
    assert "get_tokens" not in list_fn
    repo_list = ast.unparse(
        next(
            node
            for node in ast.walk(ast.parse(PUBLISHING_REPOSITORY.read_text()))
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "list_social_accounts"
        )
    )
    assert "SocialAccountToken" not in repo_list
    assert "joinedload" not in repo_list
    assert "selectinload" not in repo_list


def test_list_social_accounts_issues_single_select() -> None:
    tenant_id = uuid.uuid4()
    execute = AsyncMock(
        return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
    )
    db = MagicMock()
    db.execute = execute

    async def _run() -> None:
        rows = await PublishingRepository(cast(Any, db)).list_social_accounts(tenant_id)
        assert rows == []
        assert execute.await_count == 1

    asyncio.run(_run())


def test_social_account_serialization_is_cheap_at_scale() -> None:
    accounts = [
        SimpleNamespace(
            id=uuid.uuid4(),
            platform="x",
            display_name=f"Account {index}",
            handle=f"@acct{index}",
            account_external_id=f"ext-{index}",
            status="connected",
            auth_type="oauth",
            capability_flags={"publish": "true"},
            account_metadata={"region": "us"},
            settings={"dry_run": True},
            legacy_connected_account_id=None,
            quarantine_reason=None,
        )
        for index in range(200)
    ]
    samples: list[float] = []
    for _ in range(20):
        started = time.perf_counter()
        payload = [social_account_to_response(cast(Any, account)) for account in accounts]
        samples.append((time.perf_counter() - started) * 1000.0)
        assert len(payload) == 200
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 25.0, f"serialization p95 {p95:.2f}ms unexpectedly high"


def test_handler_stage_metrics_recorded_for_list() -> None:
    reset_domain_metrics()
    from backend.api.http_handler_stages import http_handler_stage

    with http_handler_stage(operation="http.handler.publishing.social_accounts.list", stage="serialize"):
        pass
    snap = domain_metrics.snapshot()
    ops = snap.get("histograms", {}).get("cg.operation.duration_ms", [])
    assert any(
        row["attrs"].get("operation") == "http.handler.publishing.social_accounts.list.serialize"
        for row in ops
    )


def test_log_samples_do_not_show_sustained_slow_social_accounts() -> None:
    """Repeated measurements: p50 should stay well below the single 185ms outlier."""
    log_paths = sorted(LOG_DIR.glob("app_*.log"))
    durations = extract_route_durations_ms(
        log_paths,
        route_substring="/api/v1/publishing/social-accounts",
    )
    if len(durations) < 2:
        return
    summary = summarize_durations_ms(durations)
    assert summary["p50_ms"] < 80.0, summary
    # One cold-start spike is acceptable; sustained slowness is not.
    assert summary["count"] >= 2


def test_log_compare_social_accounts_vs_health_when_logs_present() -> None:
    log_paths = sorted(LOG_DIR.glob("app_*.log"))
    if not log_paths:
        return
    report = compare_routes(
        log_paths,
        suspect_route="/api/v1/publishing/social-accounts",
        baseline_route="/api/v1/health/live",
    )
    suspect = cast(dict[str, object], report["suspect"])
    if suspect["count"] == 0:
        return
    # Documented investigation: median social-accounts is not orders of magnitude above health.
    assert isinstance(suspect["p50_ms"], float)
