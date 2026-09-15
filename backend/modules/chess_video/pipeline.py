"""Sync chess video render pipeline (Pillow frames → FFmpeg)."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.modules.chess_video.encoder import EncodedVideo, encode_frames_to_mp4
from backend.modules.chess_video.frames import generate_position_frames
from backend.modules.chess_video.parser import ParsedChessGame
from backend.modules.chess_video.presets import RenderPreset, get_preset
from backend.modules.chess_video.renderer import ChessVideoRenderer


@dataclass(frozen=True, slots=True)
class PipelineArtifacts:
    work_dir: Path
    video: EncodedVideo
    thumbnail_path: Path


def render_chess_video(
    game: ParsedChessGame,
    *,
    render_preset: str,
    seconds_per_move: float,
    include_coordinates: bool,
    include_move_text: bool,
    title: str | None,
    board_theme: str | None = None,
    work_dir: Path | None = None,
) -> PipelineArtifacts:
    """Generate frames and encode MP4 under a temp directory (caller deletes work_dir)."""
    preset: RenderPreset = get_preset(render_preset)
    root = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="chess_video_"))
    frames_dir = root / "frames"
    output_path = root / "output.mp4"

    renderer = ChessVideoRenderer(preset, board_theme=board_theme)
    frames = generate_position_frames(
        game,
        frames_dir,
        renderer=renderer,
        seconds_per_move=seconds_per_move,
        title=title,
        include_coordinates=include_coordinates,
        include_move_text=include_move_text,
    )
    encoded = encode_frames_to_mp4(
        frame_paths=frames.frame_paths,
        durations=frames.durations,
        output_path=output_path,
        preset=preset,
        work_dir=root,
    )
    # Copy thumbnail aside so frames dir can be removed while keeping the still.
    thumb = root / "thumbnail.png"
    shutil.copy2(frames.thumbnail_path, thumb)
    return PipelineArtifacts(work_dir=root, video=encoded, thumbnail_path=thumb)


def cleanup_pipeline(artifacts: PipelineArtifacts | None) -> None:
    if artifacts is None:
        return
    shutil.rmtree(artifacts.work_dir, ignore_errors=True)
