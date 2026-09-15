"""Reproducible Phase 0 performance-baseline contract.

The versioned measurements are captured outside ordinary CI against a disposable,
seeded PostgreSQL database and a local production frontend build. CI validates the
measurement provenance, coverage, and regression-threshold calculations without
turning noisy wall-clock timings into pass/fail assertions.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

BASELINE_DIR = Path(__file__).resolve().parents[3] / "docs" / "benchmarks"
BASELINE_FILE = BASELINE_DIR / "baseline.json"

BACKEND_SCENARIOS = {
    "source_ingestion",
    "duplicate_detection",
    "source_health",
    "story_clustering",
    "content_generation",
    "publishing_claim_recovery",
    "analytics_sync",
    "major_list_endpoints",
}
LATENCY_PERCENTILES = ("p50_ms", "p95_ms", "p99_ms")
REQUIRED_METRICS = {
    "latency",
    "db_query_count",
    "db_total_ms",
    "connection_checkout_ms",
    "external_provider_calls",
    "cache",
    "task_duration_ms",
    "rows_scanned",
    "peak_memory_mb",
}


def _load_baseline() -> dict[str, Any]:
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def _assert_percentiles(metric: dict[str, Any]) -> None:
    values = [metric[name] for name in LATENCY_PERCENTILES]
    assert all(isinstance(value, (int, float)) and value >= 0 for value in values)
    assert values == sorted(values), "latency percentiles must be monotonic"


def test_baseline_fixture_has_complete_scenario_coverage() -> None:
    payload = _load_baseline()
    assert payload["version"] == 2
    assert set(payload["scenarios"]) == BACKEND_SCENARIOS
    assert set(payload["frontend"]) == {"bundle", "web_vitals"}


@pytest.mark.parametrize("scenario_id", sorted(BACKEND_SCENARIOS))
def test_backend_measurements_are_complete_and_reproducible(scenario_id: str) -> None:
    scenario = _load_baseline()["scenarios"][scenario_id]
    assert scenario["seed"]["random_seed"] == 20260915
    assert scenario["sample_count"] >= 5
    assert scenario["warmup_count"] >= 1
    assert scenario["capture_command"]
    assert set(scenario["observed"]) == REQUIRED_METRICS

    observed = scenario["observed"]
    _assert_percentiles(observed["latency"])
    _assert_percentiles(observed["connection_checkout_ms"])
    _assert_percentiles(observed["task_duration_ms"])
    for name in (
        "db_query_count",
        "db_total_ms",
        "external_provider_calls",
        "rows_scanned",
        "peak_memory_mb",
    ):
        assert isinstance(observed[name], (int, float)) and observed[name] >= 0, name

    cache = observed["cache"]
    assert set(cache) == {"hits", "misses", "hit_ratio"}
    requests = cache["hits"] + cache["misses"]
    expected_ratio = cache["hits"] / requests if requests else 0.0
    assert math.isclose(cache["hit_ratio"], expected_ratio, abs_tol=0.0001)


@pytest.mark.parametrize("scenario_id", sorted(BACKEND_SCENARIOS))
def test_thresholds_derive_from_observed_p95(scenario_id: str) -> None:
    scenario = _load_baseline()["scenarios"][scenario_id]
    observed_p95 = scenario["observed"]["latency"]["p95_ms"]
    regression_factor = scenario["thresholds"]["regression_factor"]
    expected = round(observed_p95 * regression_factor, 3)
    assert scenario["thresholds"]["latency_p95_ms"] == expected
    budget = scenario["thresholds"]["db_query_count_max"]
    observed_queries = scenario["observed"]["db_query_count"]
    assert isinstance(budget, int)
    assert budget >= observed_queries


@pytest.mark.parametrize(
    "scenario_id",
    [
        "source_ingestion",
        "duplicate_detection",
        "publishing_claim_recovery",
        "major_list_endpoints",
    ],
)
def test_important_sql_has_explain_analyze_buffers_evidence(scenario_id: str) -> None:
    plans = _load_baseline()["scenarios"][scenario_id]["sql_plans"]
    assert plans, scenario_id
    for plan in plans:
        assert plan["command"].startswith("EXPLAIN (ANALYZE, BUFFERS")
        assert plan["execution_ms"] >= 0
        assert plan["actual_rows"] >= 0
        assert plan["rows_scanned"] >= plan["actual_rows"]
        assert plan["shared_hit_blocks"] >= 0
        assert plan["shared_read_blocks"] >= 0


def test_frontend_bundle_and_web_vitals_are_measured() -> None:
    frontend = _load_baseline()["frontend"]
    bundle = frontend["bundle"]
    assert bundle["sample_count"] >= 1
    assert bundle["observed"]["entry_js_kb"] > 0
    assert bundle["observed"]["largest_js_chunk_kb"] >= bundle["observed"]["entry_js_kb"]
    assert bundle["thresholds"]["entry_js_kb"] == round(
        bundle["observed"]["entry_js_kb"] * bundle["thresholds"]["regression_factor"], 3
    )
    assert bundle["thresholds"]["largest_js_chunk_kb"] == round(
        bundle["observed"]["largest_js_chunk_kb"] * bundle["thresholds"]["regression_factor"], 3
    )

    vitals = frontend["web_vitals"]
    assert vitals["sample_count"] >= 5
    for name in ("lcp_ms", "inp_ms", "cls"):
        _assert_percentiles(vitals["observed"][name])
    assert vitals["interaction"]
    factor = vitals["thresholds"]["regression_factor"]
    assert vitals["thresholds"]["lcp_p95_ms"] == round(
        vitals["observed"]["lcp_ms"]["p95_ms"] * factor, 1
    )
    assert vitals["thresholds"]["inp_p95_ms"] == round(
        vitals["observed"]["inp_ms"]["p95_ms"] * factor, 1
    )
    assert vitals["thresholds"]["cls_p95"] == round(
        vitals["observed"]["cls"]["p95_ms"] * factor, 6
    )


def test_critical_query_budgets_block_n1_regression() -> None:
    """Hard ceilings for flows Phase 2/6 fixed — prevent silent N+1 return."""
    payload = _load_baseline()
    ceilings = {
        "duplicate_detection": 2,
        "source_ingestion": 2,
        "publishing_claim_recovery": 3,
        "major_list_endpoints": 5,
    }
    for scenario_id, ceiling in ceilings.items():
        budget = payload["scenarios"][scenario_id]["thresholds"]["db_query_count_max"]
        assert budget <= ceiling, scenario_id


def test_pre_change_gate_failures_are_recorded() -> None:
    gates = _load_baseline()["pre_change_quality_gates"]
    assert gates["captured_before_phase_changes"] is True
    assert gates["failed"], "Phase 0 must preserve the pre-change failure record"
    assert all(item["command"] and item["summary"] for item in gates["failed"])
    assert all(item["command"] and item["summary"] for item in gates["passed"])
