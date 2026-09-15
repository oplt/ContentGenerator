"""
Deterministic performance baseline harness (T0.2).

Live PostgreSQL EXPLAIN / provider timing require disposable seeded data.
These tests record structural counters against stubs so later P1 tasks have
named regression thresholds even when infra is offline.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

BASELINE_DIR = Path(__file__).resolve().parents[3] / "docs" / "benchmarks"
BASELINE_FILE = BASELINE_DIR / "baseline.json"


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE_FILE.read_text())


def test_baseline_fixture_exists() -> None:
    assert BASELINE_FILE.is_file(), "docs/benchmarks/baseline.json missing"
    payload = _load_baseline()
    for key in ("scenarios", "frontend", "thresholds"):
        assert key in payload


@pytest.mark.parametrize(
    "scenario_id",
    ["ingestion_poll", "analytics_sync", "content_generation", "publishing_due_jobs"],
)
def test_scenario_has_named_thresholds(scenario_id: str) -> None:
    payload = _load_baseline()
    scenario = payload["scenarios"][scenario_id]
    assert "description" in scenario
    assert "metrics" in scenario
    for metric_name, metric in scenario["metrics"].items():
        assert "p95_ms" in metric or "max_count" in metric, metric_name
        assert "regression_factor" in metric


def test_stub_ingestion_query_budget() -> None:
    """Stub: one due-source claim + one bulk duplicate check (target shape for T3.x)."""
    payload = _load_baseline()
    budget = payload["scenarios"]["ingestion_poll"]["metrics"]["db_queries"]["max_count"]

    query_count = 0

    def pretend_list_due_sources() -> list[str]:
        nonlocal query_count
        query_count += 1
        return ["source-a", "source-b"]

    def pretend_bulk_existing_keys(keys: list[str]) -> set[str]:
        nonlocal query_count
        query_count += 1
        return set(keys[:1])

    sources = pretend_list_due_sources()
    pretend_bulk_existing_keys([f"{s}:article" for s in sources])
    assert query_count <= budget


def test_stub_analytics_sync_provider_budget() -> None:
    payload = _load_baseline()
    budget = payload["scenarios"]["analytics_sync"]["metrics"]["provider_calls"]["max_count"]
    posts = list(range(10))
    calls = 0
    started = time.perf_counter()
    for _ in posts:
        calls += 1
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert calls <= budget
    assert elapsed_ms < payload["scenarios"]["analytics_sync"]["metrics"]["wall_ms"]["p95_ms"]
