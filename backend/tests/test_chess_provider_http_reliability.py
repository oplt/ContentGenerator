"""Phase 21 — chess provider HTTP reliability (errors, timeouts, mapping)."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from backend.modules.chess_intelligence.providers.base import (
    ChessProviderAuthError,
    ChessProviderInvalidResponseError,
    ChessProviderNotFoundError,
    ChessProviderRateLimitedError,
    ChessProviderUnavailableError,
)
from backend.modules.chess_intelligence.providers.chesscom_http import map_http_error as chesscom_map
from backend.modules.chess_intelligence.providers.http_errors import (
    http_exception_for_chess_failure,
    http_exception_for_provider_error,
)
from backend.modules.chess_intelligence.providers.lichess_http import map_http_error
from backend.modules.chess_video.parser import ChessParseError


def _response(status: int, text: str = "err") -> httpx.Response:
    return httpx.Response(
        status, text=text, request=httpx.Request("GET", "https://example.test")
    )


def test_lichess_maps_auth_rate_limit_not_found() -> None:
    auth = map_http_error(provider="lichess_masters", response=_response(403), action="masters")
    assert isinstance(auth, ChessProviderAuthError)
    assert auth.code == "authentication_failure"
    assert auth.retryable is False

    limited = map_http_error(provider="lichess_puzzles", response=_response(429), action="daily")
    assert isinstance(limited, ChessProviderRateLimitedError)
    assert limited.code == "rate_limited"

    missing = map_http_error(provider="lichess_masters", response=_response(404), action="pgn")
    assert isinstance(missing, ChessProviderNotFoundError)
    assert missing.code == "not_found"

    down = map_http_error(provider="lichess_masters", response=_response(503), action="masters")
    assert isinstance(down, ChessProviderUnavailableError)
    assert down.code == "provider_unavailable"

    bad = map_http_error(provider="lichess_masters", response=_response(400), action="masters")
    assert isinstance(bad, ChessProviderInvalidResponseError)


def test_chesscom_maps_parallel_classes() -> None:
    assert isinstance(chesscom_map(_response(401), "archives"), ChessProviderAuthError)
    assert isinstance(chesscom_map(_response(429), "games"), ChessProviderRateLimitedError)
    assert isinstance(chesscom_map(_response(404), "game"), ChessProviderNotFoundError)
    assert isinstance(chesscom_map(_response(500), "game"), ChessProviderUnavailableError)


def test_http_exception_mapping_statuses() -> None:
    cases = [
        (ChessProviderNotFoundError("missing", provider="x"), 404),
        (ChessProviderAuthError("auth", provider="x"), 502),
        (ChessProviderRateLimitedError("slow", provider="x"), 429),
        (ChessProviderUnavailableError("down", provider="x"), 503),
        (ChessProviderInvalidResponseError("bad", provider="x"), 502),
    ]
    for exc, expected in cases:
        http_exc = http_exception_for_provider_error(exc)
        assert isinstance(http_exc, HTTPException)
        assert http_exc.status_code == expected
        assert "Traceback" not in str(http_exc.detail)


def test_chess_failure_helper_covers_pgn_and_db() -> None:
    pgn = http_exception_for_chess_failure(ChessParseError("bad pgn"))
    assert pgn is not None and pgn.status_code == 422

    db = http_exception_for_chess_failure(SQLAlchemyError("boom"))
    assert db is not None and db.status_code == 500
    assert db.detail == "Database failure"

    assert http_exception_for_chess_failure(RuntimeError("other")) is None


def test_providers_use_shared_http_client() -> None:
    root = Path(__file__).resolve().parents[1] / "modules" / "chess_intelligence" / "providers"
    for name in ("lichess_http.py", "chesscom_http.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "from backend.core.http import" in src
        assert "build_timeout" in src
        assert "max_retries" in src
