"""Deterministic Stockfish analysis identity (§12) — not job UUID."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Bump when ply schema / critical-moment heuristics change result semantics.
ANALYSIS_SCHEMA_VERSION = "chess_analysis.v1"

ENGINE_IMPLEMENTATION = "stockfish"


def normalize_analysis_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Canonical settings blob for fingerprinting (result-affecting knobs only)."""
    depth = settings.get("depth")
    time_limit = settings.get("time_limit_seconds")
    return {
        "depth": int(depth) if depth is not None else None,
        "time_limit_seconds": (
            float(time_limit) if time_limit is not None else None
        ),
        "hash_mb": int(settings.get("hash_mb") or 64),
        "threads": int(settings.get("threads") or 1),
        "multipv": int(settings.get("multipv") or 1),
        "score_perspective": str(settings.get("score_perspective") or "white"),
    }


def engine_version_label(*, stockfish_path: str, override: str | None = None) -> str:
    """Stable engine identity at enqueue time (avoid opening binary every request)."""
    if override and override.strip():
        return override.strip()
    name = Path(stockfish_path or "").expanduser().name
    return name or "unconfigured"


def compute_analysis_fingerprint(
    *,
    game_fingerprint: str,
    engine_name: str = ENGINE_IMPLEMENTATION,
    engine_version: str,
    analysis_schema_version: str = ANALYSIS_SCHEMA_VERSION,
    analysis_settings: dict[str, Any],
) -> str:
    """SHA256 identity for reusable analysis (game + engine + schema + settings)."""
    normalized = normalize_analysis_settings(analysis_settings)
    payload = {
        "game_fingerprint": game_fingerprint.strip(),
        "engine_name": engine_name.strip().lower(),
        "engine_version": engine_version.strip(),
        "analysis_schema_version": analysis_schema_version.strip(),
        "settings": normalized,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
