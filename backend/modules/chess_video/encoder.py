"""Single-pass FFmpeg encoding for chess video frames."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import settings
from backend.modules.chess_video.presets import RenderPreset

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EncodedVideo:
    output_path: Path
    duration_seconds: float
    width: int
    height: int
    file_size_bytes: int


class ChessVideoEncoderError(RuntimeError):
    """Raised when FFmpeg encoding fails."""


def write_concat_manifest(
    frame_paths: list[Path],
    durations: list[float],
    manifest_path: Path,
) -> Path:
    """Write an FFmpeg concat demuxer file with per-frame durations."""
    if len(frame_paths) != len(durations):
        raise ValueError("frame_paths and durations length mismatch")
    if not frame_paths:
        raise ValueError("No frames to encode")

    lines: list[str] = []
    for path, duration in zip(frame_paths, durations, strict=True):
        # Concat demuxer requires escaped single quotes in paths.
        safe = str(path.resolve()).replace("'", r"'\''")
        lines.append(f"file '{safe}'")
        lines.append(f"duration {duration:.4f}")
    # Repeat last file once so the final duration is honored.
    last = str(frame_paths[-1].resolve()).replace("'", r"'\''")
    lines.append(f"file '{last}'")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest_path


def encode_frames_to_mp4(
    *,
    frame_paths: list[Path],
    durations: list[float],
    output_path: Path,
    preset: RenderPreset,
    work_dir: Path,
) -> EncodedVideo:
    """Encode all position frames with a single FFmpeg process."""
    manifest_path = work_dir / "frames.concat.txt"
    write_concat_manifest(frame_paths, durations, manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        settings.FFMPEG_BIN,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest_path),
        "-vf",
        f"scale={preset.width}:{preset.height}:flags=lanczos,fps={preset.fps},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        preset.encoder_preset,
        "-crf",
        str(preset.crf),
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ChessVideoEncoderError(
            f"FFmpeg binary not found: {settings.FFMPEG_BIN}"
        ) from exc

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        logger.error("chess video ffmpeg failed: %s", stderr[-2000:])
        raise ChessVideoEncoderError(
            f"FFmpeg encoding failed (exit {completed.returncode}): {stderr[-500:]}"
        )

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise ChessVideoEncoderError("FFmpeg completed but output MP4 is missing or empty.")

    return EncodedVideo(
        output_path=output_path,
        duration_seconds=float(sum(durations)),
        width=preset.width,
        height=preset.height,
        file_size_bytes=output_path.stat().st_size,
    )
