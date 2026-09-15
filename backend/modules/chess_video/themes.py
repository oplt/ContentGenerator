"""Chess board visual themes for the Pillow renderer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BoardThemeName = Literal[
    "classic_wood",
    "tournament_green",
    "midnight_blue",
    "slate",
    "high_contrast",
]

DEFAULT_BOARD_THEME: BoardThemeName = "classic_wood"

Rgb = tuple[int, int, int]
Rgba = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class BoardTheme:
    name: BoardThemeName
    label: str
    light: Rgb
    dark: Rgb
    highlight_from: Rgba
    highlight_to: Rgba
    edge: Rgb


BOARD_THEMES: dict[BoardThemeName, BoardTheme] = {
    "classic_wood": BoardTheme(
        name="classic_wood",
        label="Classic wood",
        light=(240, 217, 181),
        dark=(181, 136, 99),
        highlight_from=(246, 246, 105, 140),
        highlight_to=(186, 202, 68, 160),
        edge=(40, 48, 58),
    ),
    "tournament_green": BoardTheme(
        name="tournament_green",
        label="Tournament green",
        light=(235, 236, 208),
        dark=(119, 149, 86),
        highlight_from=(255, 255, 120, 150),
        highlight_to=(186, 202, 68, 170),
        edge=(45, 60, 40),
    ),
    "midnight_blue": BoardTheme(
        name="midnight_blue",
        label="Midnight blue",
        light=(222, 227, 235),
        dark=(62, 106, 225),  # Electric Blue-aligned dark square
        highlight_from=(255, 220, 100, 150),
        highlight_to=(120, 180, 255, 160),
        edge=(24, 32, 48),
    ),
    "slate": BoardTheme(
        name="slate",
        label="Slate",
        light=(232, 234, 237),
        dark=(92, 94, 98),
        highlight_from=(246, 246, 140, 140),
        highlight_to=(140, 160, 200, 150),
        edge=(35, 38, 42),
    ),
    "high_contrast": BoardTheme(
        name="high_contrast",
        label="High contrast",
        light=(255, 255, 255),
        dark=(40, 40, 40),
        highlight_from=(255, 230, 0, 160),
        highlight_to=(0, 180, 255, 150),
        edge=(20, 20, 20),
    ),
}


def get_board_theme(name: str | None = None) -> BoardTheme:
    key = (name or DEFAULT_BOARD_THEME).strip().lower()
    if key not in BOARD_THEMES:
        raise ValueError(f"Unknown board theme: {name}")
    return BOARD_THEMES[key]  # type: ignore[index]


def list_board_themes() -> list[BoardTheme]:
    return list(BOARD_THEMES.values())
