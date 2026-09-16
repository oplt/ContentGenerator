"""Chess video render / encode presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RenderPresetName = Literal[
    "economy_vertical",
    "social_vertical",
    "square",
    "horizontal",
]

DEFAULT_PRESET: RenderPresetName = "economy_vertical"


@dataclass(frozen=True, slots=True)
class RenderPreset:
    name: RenderPresetName
    width: int
    height: int
    fps: int
    encoder_preset: str
    crf: int


PRESETS: dict[RenderPresetName, RenderPreset] = {
    "economy_vertical": RenderPreset(
        name="economy_vertical",
        width=720,
        height=1280,
        fps=24,
        encoder_preset="ultrafast",
        crf=26,
    ),
    "social_vertical": RenderPreset(
        name="social_vertical",
        width=1080,
        height=1920,
        fps=30,
        encoder_preset="veryfast",
        crf=23,
    ),
    "square": RenderPreset(
        name="square",
        width=1080,
        height=1080,
        fps=30,
        encoder_preset="veryfast",
        crf=23,
    ),
    "horizontal": RenderPreset(
        name="horizontal",
        width=1920,
        height=1080,
        fps=30,
        encoder_preset="veryfast",
        crf=23,
    ),
}


def get_preset(name: str | None = None) -> RenderPreset:
    key = (name or DEFAULT_PRESET).strip().lower()
    if key not in PRESETS:
        raise ValueError(f"Unknown render preset: {name}")
    return PRESETS[key]
