"""Daily puzzle freshness helpers (§10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.modules.chess_intelligence.daily_freshness import (
    daily_puzzle_response,
    utc_day,
)
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    stamp_ingestion_mode,
)
from backend.modules.chess_intelligence.normalizer import chess_puzzle_from_fields


def test_utc_day_formats_iso_date() -> None:
    assert utc_day(now=datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)) == "2026-09-16"


def test_daily_puzzle_response_marks_fresh_for_today() -> None:
    today = "2026-09-16"
    now = datetime(2026, 9, 16, 1, 0, tzinfo=timezone.utc)
    puzzle = chess_puzzle_from_fields(
        tenant_id=uuid.uuid4(),
        external_id="d1",
        provider="lichess_puzzles",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        solution_moves_uci=["e2e4"],
        solution_moves_san=["e4"],
        source_metadata=stamp_ingestion_mode(
            {"daily_utc": today, "via": "daily_puzzle_sync"},
            ChessIngestionMode.PUZZLE_SYNC,
        ),
        retrieved_at=now,
    )
    puzzle.created_at = now
    puzzle.updated_at = now
    puzzle.id = uuid.uuid4()
    resp = daily_puzzle_response(puzzle, today_utc=today)
    assert resp.is_stale is False
    assert resp.freshness == "fresh"
    assert resp.daily_utc == today
    assert resp.retrieved_at is not None


def test_daily_puzzle_response_marks_stale_for_prior_day() -> None:
    now = datetime(2020, 1, 1, tzinfo=timezone.utc)
    puzzle = chess_puzzle_from_fields(
        tenant_id=uuid.uuid4(),
        external_id="d-old",
        provider="lichess_puzzles",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        solution_moves_uci=["e2e4"],
        solution_moves_san=["e4"],
        source_metadata=stamp_ingestion_mode(
            {"daily_utc": "2020-01-01", "via": "daily_puzzle_sync"},
            ChessIngestionMode.PUZZLE_SYNC,
        ),
        retrieved_at=now,
    )
    puzzle.created_at = now
    puzzle.updated_at = now
    puzzle.id = uuid.uuid4()
    resp = daily_puzzle_response(puzzle, today_utc="2026-09-16")
    assert resp.is_stale is True
    assert resp.freshness == "stale"
    assert resp.daily_utc == "2020-01-01"
