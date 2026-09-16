"""Phase 31 — chess observability helpers emit logs + domain metrics."""

from __future__ import annotations

from backend.core.domain_metrics import (
    METRIC_CHESS_IMPORT,
    METRIC_OPERATION_TOTAL,
    domain_metrics,
    reset_domain_metrics,
)
from backend.modules.chess_intelligence.observability import (
    OP_ENGINE_ANALYZE,
    OP_VIDEO_HANDOFF,
    log_provider_request,
    record_engine_analysis,
    record_game_import_progress,
    record_puzzle_import_progress,
    record_video_handoff,
)


def setup_function() -> None:
    reset_domain_metrics()


def test_game_import_progress_increments_import_metric() -> None:
    record_game_import_progress(
        provider="pgn_archive",
        inserted=3,
        linked=1,
        duplicates=2,
        invalid=1,
        scanned=7,
    )
    snap = domain_metrics.snapshot()
    rows = snap["counters"][METRIC_CHESS_IMPORT]
    by_result = {row["attrs"]["result"]: row["value"] for row in rows}
    assert by_result["inserted"] == 3
    assert by_result["linked"] == 1
    assert by_result["duplicate"] == 2
    assert by_result["invalid"] == 1


def test_puzzle_import_and_engine_metrics() -> None:
    record_puzzle_import_progress(
        provider="lichess_puzzles",
        inserted=5,
        duplicates=2,
        invalid=1,
        filtered=4,
        scanned=12,
    )
    record_engine_analysis(
        outcome="success",
        duration_ms=1234.5,
        ply_count=40,
        engine_name="Stockfish",
    )
    record_engine_analysis(
        outcome="failure",
        duration_ms=10.0,
        error_class="config_error",
    )
    snap = domain_metrics.snapshot()
    puzzle_rows = [
        row
        for row in snap["counters"][METRIC_CHESS_IMPORT]
        if row["attrs"].get("operation") == "chess.puzzle.import"
    ]
    assert any(row["attrs"]["result"] == "filtered" and row["value"] == 4 for row in puzzle_rows)
    ops = [
        row
        for row in snap["counters"][METRIC_OPERATION_TOTAL]
        if row["attrs"].get("operation") == OP_ENGINE_ANALYZE
    ]
    outcomes = {row["attrs"]["outcome"] for row in ops}
    assert "success" in outcomes
    assert "failure" in outcomes


def test_video_handoff_and_provider_log_helpers() -> None:
    record_video_handoff(
        outcome="success",
        source="famous",
        cached=False,
        is_famous=True,
        duration_ms=25.0,
    )
    log_provider_request(
        provider="lichess_masters",
        action="/masters",
        outcome="success",
        duration_ms=40.0,
        status_class="2xx",
    )
    snap = domain_metrics.snapshot()
    handoffs = [
        row
        for row in snap["counters"][METRIC_CHESS_IMPORT]
        if row["attrs"].get("operation") == OP_VIDEO_HANDOFF
    ]
    assert any(row["attrs"]["provider"] == "famous" and row["attrs"]["result"] == "queued" for row in handoffs)
    assert any(
        row["attrs"].get("operation") == OP_VIDEO_HANDOFF and row["attrs"]["outcome"] == "success"
        for row in snap["counters"][METRIC_OPERATION_TOTAL]
    )


def test_observability_doc_exists() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs" / "chess-observability.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "chess_provider_request" in text
    assert "cg.chess.import.total" in text
    assert "chess.engine.analyze" in text
    assert "discovered" in text
    assert "high_water_mark" in text
    assert "sanitize_log_payload" in text or "Never** log full PGNs" in text or "Never log" in text
