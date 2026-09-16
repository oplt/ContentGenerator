"""Phase 32 — chess documentation covers required operator topics."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"

REQUIRED_TOPICS = (
    "supported chess providers",
    "configuration",
    "historical game import",
    "puzzle import",
    "source provenance",
    "famous-game catalog",
    "stockfish",
    "api routes",
    "frontend workflow",
    "game → video",
    "example developer commands",
)

REQUIRED_COMMAND_MARKERS = (
    "import_chess_pgn",
    "import_lichess_puzzles",
    "apply_famous_catalog",
    "STOCKFISH_PATH",
    "/api/v1/chess",
    "/dashboard/chess-video",
)

RELATED_DOCS = (
    "chess.md",
    "chess-configuration.md",
    "chess-observability.md",
    "chess-dependency-policy.md",
    "chess-backend-structure.md",
    "chess-frontend-structure.md",
    "chess-ux-requirements.md",
    "chess-video.md",
    "chess-intelligence-phase1.md",
)


def test_chess_guide_covers_phase32_topics() -> None:
    guide = (DOCS / "chess.md").read_text(encoding="utf-8").lower()
    missing = [topic for topic in REQUIRED_TOPICS if topic not in guide]
    assert missing == [], f"docs/chess.md missing topics: {missing}"


def test_chess_guide_includes_developer_commands() -> None:
    text = (DOCS / "chess.md").read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_COMMAND_MARKERS if marker not in text]
    assert missing == [], f"docs/chess.md missing command markers: {missing}"


def test_related_chess_docs_exist() -> None:
    missing = [name for name in RELATED_DOCS if not (DOCS / name).is_file()]
    assert missing == [], f"missing chess docs: {missing}"


def test_readme_points_at_chess_guide() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "docs/chess.md" in readme
