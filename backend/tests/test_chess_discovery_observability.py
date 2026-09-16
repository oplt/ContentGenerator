"""§20 — discovery/persistence counters + no PGN/secrets in logs."""

from __future__ import annotations

from backend.core.domain_metrics import METRIC_OPERATION_TOTAL, domain_metrics, reset_domain_metrics
from backend.modules.chess_intelligence.observability import (
    OP_CATALOG_DISCOVERY,
    SENSITIVE_LOG_KEYS,
    DiscoveryPersistenceStats,
    record_discovery_persistence,
    sanitize_log_payload,
    stats_from_pgn_progress,
    stats_from_provider_sync,
    stats_from_puzzle_progress,
)


def setup_function() -> None:
    reset_domain_metrics()


def test_sanitize_redacts_pgn_and_tokens() -> None:
    assert "pgn" in SENSITIVE_LOG_KEYS
    cleaned = sanitize_log_payload(
        {
            "provider": "lichess_masters",
            "pgn": '[Event "X"]\n\n1. e4 e5 1-0\n',
            "api_token": "secret-value",
            "normalized_pgn": "1. e4 e5",
            "new_games": 2,
        }
    )
    assert cleaned["provider"] == "lichess_masters"
    assert cleaned["new_games"] == 2
    assert cleaned["pgn"] == "[redacted]"
    assert cleaned["api_token"] == "[redacted]"
    assert cleaned["normalized_pgn"] == "[redacted]"


def test_discovery_stats_expose_prompt_counters() -> None:
    stats = stats_from_provider_sync(
        searched=10,
        in_window=8,
        attempted=5,
        inserted=2,
        linked=1,
        dupes=2,
        errors=0,
        duration_ms=12.5,
        high_water_mark="2026-09-16T00:00:00+00:00",
    )
    result = stats.as_result()
    for key in (
        "discovered",
        "fetched",
        "parsed",
        "normalized",
        "new_games",
        "existing_games",
        "new_sources",
        "duplicate_sources",
        "skipped",
        "invalid",
        "persisted",
        "failed",
        "duration_ms",
        "high_water_mark",
    ):
        assert key in result
    assert result["discovered"] == 10
    assert result["new_games"] == 2
    assert result["inserted"] == 2  # legacy alias
    assert result["failed"] == 0


def test_pgn_and_puzzle_stats_aliases() -> None:
    pgn = stats_from_pgn_progress(
        scanned=7,
        inserted=3,
        linked_source=1,
        skipped_duplicate=2,
        skipped_filtered=1,
        skipped_error=0,
    ).as_result()
    assert pgn["discovered"] == 7
    assert pgn["skipped"] == 1
    assert pgn["persisted"] == 4
    puzzle = stats_from_puzzle_progress(
        scanned=12, inserted=5, skipped_duplicate=2, filtered=4, skipped_error=1
    ).as_result()
    assert puzzle["persisted"] == 5
    assert puzzle["skipped"] == 4
    assert puzzle.get("puzzle") is True


def test_record_discovery_persistence_emits_operation_metric() -> None:
    stats = DiscoveryPersistenceStats(discovered=3, new_games=1, persisted=1, failed=0)
    record_discovery_persistence(
        kind="game",
        provider="lichess_masters",
        stats=stats,
        include_import_counters=True,
    )
    snap = domain_metrics.snapshot()
    ops = [
        row
        for row in snap["counters"][METRIC_OPERATION_TOTAL]
        if row["attrs"].get("operation") == OP_CATALOG_DISCOVERY
    ]
    assert ops
    assert ops[0]["attrs"]["outcome"] == "success"
