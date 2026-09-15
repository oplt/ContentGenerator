"""Low-resource sequential PNG frame generation for chess videos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess

from backend.modules.chess_video.parser import ParsedChessGame
from backend.modules.chess_video.renderer import ChessVideoRenderer, FrameMeta


@dataclass(frozen=True, slots=True)
class GeneratedFrames:
    directory: Path
    frame_paths: list[Path]
    durations: list[float]
    thumbnail_path: Path


def generate_position_frames(
    game: ParsedChessGame,
    output_dir: Path,
    *,
    renderer: ChessVideoRenderer,
    seconds_per_move: float = 1.0,
    opening_hold_seconds: float | None = None,
    final_hold_seconds: float | None = None,
    title: str | None = None,
    include_coordinates: bool = True,
    include_move_text: bool = True,
    compress_level: int = 1,
) -> GeneratedFrames:
    """Write one PNG per board position; never keep all images in RAM."""
    output_dir.mkdir(parents=True, exist_ok=True)
    open_hold = opening_hold_seconds if opening_hold_seconds is not None else seconds_per_move
    end_hold = final_hold_seconds if final_hold_seconds is not None else max(seconds_per_move * 1.5, 1.2)

    board = chess.Board(game.starting_fen)
    frame_paths: list[Path] = []
    durations: list[float] = []
    last_move: chess.Move | None = None
    last_san: str | None = None
    move_number: int | None = None

    base_meta = FrameMeta(
        title=title or game.event,
        white_player=game.white_player,
        black_player=game.black_player,
        event=game.event,
        result=None,
        show_coordinates=include_coordinates,
    )

    def _write(index: int, duration: float, meta: FrameMeta) -> Path:
        path = output_dir / f"frame_{index:04d}.png"
        image = renderer.render_frame(board, last_move=last_move, meta=meta)
        try:
            image.save(path, format="PNG", compress_level=compress_level)
        finally:
            image.close()
        frame_paths.append(path)
        durations.append(duration)
        return path

    # Starting position (no last-move highlight).
    _write(0, open_hold, base_meta)

    for ply_index, (move, san) in enumerate(zip(game.moves, game.san_moves, strict=True), start=1):
        # fullmove_number is the move about to be played; capture before push.
        move_number = board.fullmove_number
        board.push(move)
        last_move = move
        last_san = san if include_move_text else None

        is_last = ply_index == len(game.moves)
        duration = end_hold if is_last else seconds_per_move
        meta = FrameMeta(
            title=base_meta.title,
            white_player=base_meta.white_player,
            black_player=base_meta.black_player,
            event=base_meta.event,
            move_number=move_number if include_move_text else None,
            last_san=last_san,
            result=game.result if is_last else None,
            show_coordinates=include_coordinates,
        )
        _write(ply_index, duration, meta)

    if not frame_paths:
        raise RuntimeError("No frames generated.")

    return GeneratedFrames(
        directory=output_dir,
        frame_paths=frame_paths,
        durations=durations,
        thumbnail_path=frame_paths[-1],
    )
