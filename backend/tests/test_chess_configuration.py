"""Phase 30 — chess configuration: .env.example completeness + no client secrets."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

# Settings fields that chess code paths actually read (must appear in .env.example).
REQUIRED_ENV_KEYS = (
    "LICHESS_API_TOKEN",
    "LICHESS_API_BASE_URL",
    "LICHESS_EXPLORER_BASE_URL",
    "LICHESS_HTTP_TIMEOUT_SECONDS",
    "LICHESS_HTTP_MAX_RETRIES",
    "LICHESS_RATE_LIMIT_RPH",
    "CHESSCOM_API_BASE_URL",
    "CHESSCOM_USER_AGENT",
    "CHESSCOM_HTTP_TIMEOUT_SECONDS",
    "CHESSCOM_HTTP_MAX_RETRIES",
    "CHESSCOM_RATE_LIMIT_RPH",
    "HTTP_PROVIDER_LICHESS_CONCURRENCY",
    "HTTP_PROVIDER_CHESSCOM_CONCURRENCY",
    "CHESS_CACHE_MASTERS_SEARCH_TTL_SECONDS",
    "CHESS_CACHE_GAME_PGN_TTL_SECONDS",
    "CHESS_CACHE_PUZZLE_TTL_SECONDS",
    "CHESS_CACHE_PROVIDER_META_TTL_SECONDS",
    "CHESS_CACHE_DAILY_PUZZLE_TTL_SECONDS",
    "STOCKFISH_PATH",
    "CHESS_ENGINE_DEPTH",
    "CHESS_ENGINE_TIME_LIMIT",
    "CHESS_ENGINE_HASH_MB",
    "CHESS_ENGINE_THREADS",
)

# Prompt suggested a unified timeout; we deliberately use per-provider timeouts.
UNUSED_PROMPT_KEYS = ("CHESS_PROVIDER_TIMEOUT_SECONDS",)

# Must never appear as Vite client env (or hardcoded in frontend src).
FORBIDDEN_CLIENT_SECRETS = (
    "LICHESS_API_TOKEN",
    "STOCKFISH_PATH",
    "CHESS_ENGINE_DEPTH",
    "CHESS_ENGINE_TIME_LIMIT",
    "CHESS_ENGINE_HASH_MB",
    "CHESS_ENGINE_THREADS",
    "CHESSCOM_USER_AGENT",
)


def _env_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_env_example_lists_used_chess_settings() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    keys = _env_keys(example)
    missing = [key for key in REQUIRED_ENV_KEYS if key not in keys]
    assert missing == [], f"backend/.env.example missing used chess keys: {missing}"


def test_env_example_omits_unused_unified_timeout() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    keys = _env_keys(example)
    for key in UNUSED_PROMPT_KEYS:
        assert key not in keys, f"unused key should not be in .env.example: {key}"
    assert "LICHESS_HTTP_TIMEOUT_SECONDS" in keys
    assert "CHESSCOM_HTTP_TIMEOUT_SECONDS" in keys


def test_settings_define_required_chess_fields() -> None:
    from backend.core.config import Settings

    fields = set(Settings.model_fields)
    missing = [key for key in REQUIRED_ENV_KEYS if key not in fields]
    assert missing == [], f"Settings missing chess fields: {missing}"
    for key in UNUSED_PROMPT_KEYS:
        assert key not in fields


def test_frontend_env_has_no_chess_provider_secrets() -> None:
    example = FRONTEND / ".env.example"
    assert example.is_file()
    text = example.read_text(encoding="utf-8")
    keys = _env_keys(text)
    assert "VITE_API_BASE" in keys
    for secret in FORBIDDEN_CLIENT_SECRETS:
        assert secret not in keys
        assert f"VITE_{secret}" not in keys
        assert secret not in text


def test_frontend_source_does_not_reference_provider_tokens() -> None:
    """Scan FE sources for accidental Lichess token / Stockfish path wiring."""
    src = FRONTEND / "src"
    pattern = re.compile(
        r"VITE_.*(LICHESS|STOCKFISH|CHESS_ENGINE|CHESSCOM)|"
        r"LICHESS_API_TOKEN|STOCKFISH_PATH",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for path in src.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".env"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            hits.append(str(path.relative_to(REPO)))
    assert hits == [], f"frontend must not wire provider secrets: {hits}"


def test_configuration_doc_exists() -> None:
    path = REPO / "docs/chess-configuration.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "LICHESS_API_TOKEN" in text
    assert "STOCKFISH_PATH" in text
    assert "CHESS_PROVIDER_TIMEOUT_SECONDS" in text
    assert "Vite" in text or "frontend" in text.lower()
