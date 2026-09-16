"""Phase 32 + hybrid §32 — chess documentation covers required operator topics."""

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
    "hybrid architecture",
    "operational runbook",
    "security + external-service rules",
    "performance",
    "do not overengineer",
    "target architecture",
    "priority order",
    "critical acceptance criteria",
)

REQUIRED_COMMAND_MARKERS = (
    "import_chess_pgn",
    "import_lichess_puzzles",
    "apply_famous_catalog",
    "STOCKFISH_PATH",
    "/api/v1/chess",
    "/dashboard/chess-video",
    "/chess/sync-states",
    "provider_sync",
)

# §32 diagram + concept vocabulary (case-insensitive scan of chess.md).
HYBRID_DIAGRAM_MARKERS = (
    "external sources",
    "provider / import layer",
    "normalization",
    "fingerprint/dedupe",
    "local canonical catalog",
    "famous",
    "recent",
    "puzzles",
    "stockfish",
    "critical moments",
    "content opportunity",
    "signalforge workflow",
    "chess video",
    "review / publish",
)

HYBRID_CONCEPTS = (
    "provider",
    "source",
    "canonical game",
    "famous curation",
    "recent discovery",
    "content opportunity",
    "analysis profile",
    "sync checkpoint",
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


def test_chess_guide_documents_hybrid_architecture() -> None:
    guide = (DOCS / "chess.md").read_text(encoding="utf-8").lower()
    missing_diagram = [m for m in HYBRID_DIAGRAM_MARKERS if m not in guide]
    missing_concepts = [c for c in HYBRID_CONCEPTS if c not in guide]
    assert missing_diagram == [], f"hybrid diagram gaps: {missing_diagram}"
    assert missing_concepts == [], f"hybrid concept gaps: {missing_concepts}"


def test_related_chess_docs_exist() -> None:
    missing = [name for name in RELATED_DOCS if not (DOCS / name).is_file()]
    assert missing == [], f"missing chess docs: {missing}"


def test_readme_points_at_chess_guide() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "docs/chess.md" in readme
