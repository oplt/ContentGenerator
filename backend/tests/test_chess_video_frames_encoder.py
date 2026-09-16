"""Tests for chess video frame generation and FFmpeg encoding."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.modules.chess_video.encoder import encode_frames_to_mp4, write_concat_manifest
from backend.modules.chess_video.frames import generate_position_frames
from backend.modules.chess_video.parser import parse_chess_input
from backend.modules.chess_video.presets import get_preset
from backend.modules.chess_video.renderer import ChessVideoRenderer


def test_generate_one_png_per_position(tmp_path: Path) -> None:
    game = parse_chess_input("e2e4 e7e5 g1f3", "uci")
    renderer = ChessVideoRenderer("economy_vertical")
    result = generate_position_frames(
        game,
        tmp_path / "frames",
        renderer=renderer,
        seconds_per_move=0.5,
    )
    # starting position + 3 moves
    assert len(result.frame_paths) == 4
    assert all(p.is_file() and p.stat().st_size > 0 for p in result.frame_paths)
    assert result.frame_paths[0].name == "frame_0000.png"
    assert result.durations[0] == 0.5
    assert result.durations[-1] >= 0.5


def test_concat_manifest_includes_final_file_repeat(tmp_path: Path) -> None:
    frames = [tmp_path / "frame_0000.png", tmp_path / "frame_0001.png"]
    for path in frames:
        path.write_bytes(b"x")
    manifest = tmp_path / "frames.concat.txt"
    write_concat_manifest(frames, [1.0, 0.8], manifest)
    text = manifest.read_text(encoding="utf-8")
    assert "duration 1.0000" in text
    assert "duration 0.8000" in text
    assert text.count("file '") == 3


@pytest.mark.skipif(
    not Path("/usr/bin/ffmpeg").exists(),
    reason="ffmpeg not installed",
)
def test_single_pass_ffmpeg_encode(tmp_path: Path) -> None:
    game = parse_chess_input("1. e4 e5 2. Nf3", "san")
    preset = get_preset("economy_vertical")
    renderer = ChessVideoRenderer(preset)
    frames = generate_position_frames(
        game,
        tmp_path / "frames",
        renderer=renderer,
        seconds_per_move=0.4,
        title="Test Game",
    )
    output = tmp_path / "out.mp4"
    encoded = encode_frames_to_mp4(
        frame_paths=frames.frame_paths,
        durations=frames.durations,
        output_path=output,
        preset=preset,
        work_dir=tmp_path,
    )
    assert encoded.output_path.is_file()
    assert encoded.file_size_bytes > 1000
    assert encoded.width == 720
    assert encoded.height == 1280
    assert encoded.duration_seconds == pytest.approx(sum(frames.durations))


def test_encode_invokes_ffmpeg_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [tmp_path / "frame_0000.png", tmp_path / "frame_0001.png"]
    for path in frames:
        path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    output = tmp_path / "out.mp4"
    calls: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=True, text=True):  # noqa: ANN001
        calls.append(list(cmd))
        output.write_bytes(b"fake-mp4")
        return type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    monkeypatch.setattr("backend.modules.chess_video.encoder.subprocess.run", fake_run)
    encoded = encode_frames_to_mp4(
        frame_paths=frames,
        durations=[1.0, 0.8],
        output_path=output,
        preset=get_preset("square"),
        work_dir=tmp_path,
    )
    assert len(calls) == 1
    assert "libx264" in calls[0]
    assert encoded.file_size_bytes > 0


def test_pipeline_cleans_temp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.modules.chess_video.pipeline import cleanup_pipeline, render_chess_video

    def fake_encode(**kwargs):  # noqa: ANN001
        kwargs["output_path"].write_bytes(b"mp4")
        return type(
            "E",
            (),
            {
                "output_path": kwargs["output_path"],
                "duration_seconds": 1.0,
                "width": 720,
                "height": 1280,
                "file_size_bytes": 10,
            },
        )()

    monkeypatch.setattr("backend.modules.chess_video.pipeline.encode_frames_to_mp4", fake_encode)
    game = parse_chess_input("e2e4 e7e5", "uci")
    work = tmp_path / "work"
    work.mkdir()
    artifacts = render_chess_video(
        game,
        render_preset="economy_vertical",
        seconds_per_move=0.3,
        include_coordinates=True,
        include_move_text=True,
        title=None,
        work_dir=work,
    )
    assert artifacts.work_dir.exists()
    cleanup_pipeline(artifacts)
    assert not artifacts.work_dir.exists()
