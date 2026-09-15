"""Board theme unit tests."""

from __future__ import annotations

import chess

from backend.modules.chess_video.fingerprint import compute_render_fingerprint
from backend.modules.chess_video.renderer import ChessVideoRenderer
from backend.modules.chess_video.themes import BOARD_THEMES, get_board_theme


def test_get_board_theme_default() -> None:
    theme = get_board_theme()
    assert theme.name == "classic_wood"


def test_board_themes_render_distinct_center_colors() -> None:
    board = chess.Board()
    samples: set[tuple[int, int, int]] = set()
    for name in BOARD_THEMES:
        renderer = ChessVideoRenderer("economy_vertical", board_theme=name)
        frame = renderer.render_frame(board)
        try:
            # Sample a light-ish board square near center-left of the board region.
            samples.add(frame.getpixel((360, 640)))
        finally:
            frame.close()
    assert len(samples) == len(BOARD_THEMES)


def test_fingerprint_changes_with_board_theme() -> None:
    base = dict(
        normalized_pgn="1. e4 e5 *",
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        orientation="white",
        render_preset="economy_vertical",
        seconds_per_move=1.0,
        include_coordinates=True,
        include_move_text=True,
    )
    a = compute_render_fingerprint(**base, board_theme="classic_wood")
    b = compute_render_fingerprint(**base, board_theme="midnight_blue")
    assert a != b
