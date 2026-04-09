from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field


class RenderPreset(str, Enum):
    SQUARE = "square"
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class VisualSegment(BaseModel):
    segment: int
    prompt: str
    duration_seconds: float = 2.0


class MediaSequenceItem(BaseModel):
    kind: str = "color"
    duration_seconds: float = 2.0
    source_path: str | None = None
    background_color: str = "#0f172a"
    text: str = ""
    transition: str = "cut"


class BrandingConfig(BaseModel):
    palette: list[str] = Field(default_factory=lambda: ["#0f172a", "#1d4ed8", "#f8fafc"])
    text_color: str = "#f8fafc"
    accent_color: str = "#38bdf8"
    progress_bar: bool = True
    subtitle_burn_in: bool = True
    overlay_opacity: float = 0.28
    font_family: str = "Sans"
    intro_text: str = ""
    outro_text: str = ""


class RendererInput(BaseModel):
    platform: str
    script: str
    subtitles: list[str] = Field(default_factory=list)
    voiceover_script: str = ""
    visual_segments: list[VisualSegment] = Field(default_factory=list)
    media_sequence: list[MediaSequenceItem] = Field(default_factory=list)
    title_card: str = ""
    summary_card: str = ""
    cta: str = ""
    branding: BrandingConfig = Field(default_factory=BrandingConfig)
    preset: RenderPreset = RenderPreset.VERTICAL
    output_duration_seconds: float = 12.0
    preview_duration_seconds: float = 4.0


@dataclass(frozen=True)
class RenderArtifacts:
    video_bytes: bytes
    preview_bytes: bytes
    thumbnail_bytes: bytes
