"""Render fingerprinting for chess video cache reuse."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.modules.chess_video.renderer import RENDERER_VERSION

BOARD_THEME = "classic_wood"
PIECE_THEME = "noto_unicode_v1"


def compute_render_fingerprint(
    *,
    normalized_pgn: str,
    starting_fen: str,
    orientation: str,
    render_preset: str,
    seconds_per_move: float,
    include_coordinates: bool,
    include_move_text: bool,
    title: str | None = None,
    board_theme: str = BOARD_THEME,
    piece_theme: str = PIECE_THEME,
    renderer_version: str = RENDERER_VERSION,
) -> str:
    payload: dict[str, Any] = {
        "normalized_pgn": normalized_pgn.strip(),
        "starting_fen": starting_fen.strip(),
        "orientation": orientation.strip().lower(),
        "render_preset": render_preset.strip().lower(),
        "seconds_per_move": round(float(seconds_per_move), 4),
        "include_coordinates": bool(include_coordinates),
        "include_move_text": bool(include_move_text),
        "board_theme": board_theme,
        "piece_theme": piece_theme,
        "title": (title or "").strip(),
        "renderer_version": renderer_version,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
