"""Historical games are durable local assets — no scheduled redownload."""

from __future__ import annotations

from backend.modules.chess_intelligence.historical_assets import (
    FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS,
    IMMUTABLE_GAME_FIELDS,
    forbidden_historical_schedule_hits,
)
from backend.modules.chess_intelligence.ingestion_mode import (
    ChessIngestionMode,
    profile_for,
)
from backend.workers.celery_app import celery_app


def test_immutable_identity_fields_documented() -> None:
    assert "normalized_pgn" in IMMUTABLE_GAME_FIELDS
    assert "game_fingerprint" in IMMUTABLE_GAME_FIELDS
    assert "content_hash" in IMMUTABLE_GAME_FIELDS


def test_historical_bootstrap_does_not_need_live_http_after_import() -> None:
    profile = profile_for(ChessIngestionMode.HISTORICAL_BOOTSTRAP)
    assert profile.requires_live_http_after_import is False
    assert profile.scheduled is False
    assert profile.bulk_oriented is True


def test_celery_beat_does_not_schedule_historical_bootstrap() -> None:
    hits = forbidden_historical_schedule_hits(dict(celery_app.conf.beat_schedule or {}))
    assert hits == [], f"historical bootstrap must not be on beat: {hits}"
    assert "pgn_import" in FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS
    assert "import_chess_pgn" in FORBIDDEN_HISTORICAL_SCHEDULE_TOKENS
