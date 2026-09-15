"""Tests for chess video render fingerprinting."""

from __future__ import annotations

from backend.modules.chess_video.fingerprint import compute_render_fingerprint


def _base(**overrides):
    payload = dict(
        normalized_pgn="1. e4 e5 *",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        orientation="white",
        render_preset="economy_vertical",
        seconds_per_move=1.0,
        include_coordinates=True,
        include_move_text=True,
        title="Demo",
    )
    payload.update(overrides)
    return compute_render_fingerprint(**payload)


def test_fingerprint_stable_for_identical_inputs() -> None:
    assert _base() == _base()


def test_fingerprint_changes_with_render_option() -> None:
    a = _base(seconds_per_move=1.0)
    b = _base(seconds_per_move=1.5)
    c = _base(include_coordinates=False)
    d = _base(title="Other")
    assert len({a, b, c, d}) == 4
    assert len(a) == 64
