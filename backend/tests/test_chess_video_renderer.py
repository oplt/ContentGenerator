"""Tests for ChessVideoRenderer."""

from __future__ import annotations

import io

import chess
import pytest
from PIL import Image

from backend.modules.chess_video.presets import PRESETS, get_preset
from backend.modules.chess_video.renderer import ChessVideoRenderer, FrameMeta


def test_default_preset_is_economy_vertical() -> None:
    preset = get_preset()
    assert preset.name == "economy_vertical"
    assert preset.width == 720
    assert preset.height == 1280
    assert preset.fps == 24


@pytest.mark.parametrize("name", list(PRESETS))
def test_preset_dimensions(name: str) -> None:
    renderer = ChessVideoRenderer(name)
    board = chess.Board()
    frame = renderer.render_frame(board)
    try:
        assert frame.size == (renderer.preset.width, renderer.preset.height)
        assert frame.mode == "RGB"
    finally:
        frame.close()


def test_starting_position_png_bytes() -> None:
    renderer = ChessVideoRenderer("economy_vertical")
    png = renderer.render_png_bytes(chess.Board())
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (720, 1280)


def test_highlights_last_move() -> None:
    board = chess.Board()
    move = board.parse_san("e4")
    board.push(move)
    renderer = ChessVideoRenderer("square")
    meta = FrameMeta(
        white_player="Kasparov",
        black_player="Karpov",
        event="World Championship",
        move_number=1,
        last_san="e4",
    )
    frame = renderer.render_frame(board, last_move=move, meta=meta)
    try:
        assert frame.size == (1080, 1080)
        # Center-ish board region should not be flat background.
        sample = frame.getpixel((540, 540))
        assert sample != (18, 22, 28)
    finally:
        frame.close()


def test_board_state_changes_after_move() -> None:
    renderer = ChessVideoRenderer("economy_vertical")
    start = chess.Board()
    after = chess.Board()
    move = after.parse_san("e4")
    after.push(move)

    png_start = renderer.render_png_bytes(start)
    png_after = renderer.render_png_bytes(after, last_move=move)
    assert png_start != png_after
    assert after.piece_at(chess.E4) is not None
    assert after.piece_at(chess.E2) is None


def test_last_move_highlight_differs_from_unhighlighted() -> None:
    board = chess.Board()
    move = board.parse_san("e4")
    board.push(move)
    renderer = ChessVideoRenderer("square")
    with_hl = renderer.render_png_bytes(board, last_move=move)
    without = renderer.render_png_bytes(board, last_move=None)
    assert with_hl != without


def test_piece_cache_reuses_scaled_assets() -> None:
    renderer = ChessVideoRenderer("economy_vertical")
    board = chess.Board()
    renderer.render_frame(board).close()
    size_before = len(renderer._piece_cache)
    renderer.render_frame(board).close()
    assert len(renderer._piece_cache) == size_before
    assert size_before >= 12


def test_unknown_preset_raises() -> None:
    with pytest.raises(ValueError, match="Unknown render preset"):
        get_preset("ultra_hd")
