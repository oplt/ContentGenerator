"""§37 — target architecture maps to existing files (no diagram-only folders)."""

from __future__ import annotations

from backend.modules.chess_intelligence.target_architecture import (
    DO_NOT_CREATE_FOR_DIAGRAM_ONLY,
    TARGET_SURFACES,
    forbidden_diagram_only_folders_present,
    missing_owner_paths,
)


def test_target_surfaces_cover_prompt_concepts() -> None:
    concepts = {s.concept for s in TARGET_SURFACES}
    required = {
        "canonical game/puzzle domain",
        "providers/Lichess master discovery",
        "providers/Lichess puzzle discovery",
        "importers/historical PGN archives",
        "fingerprint + dedupe",
        "persistent provider sync state",
        "famous curation",
        "analysis/versioned Stockfish results",
        "critical moments",
        "content opportunity",
        "catalog jobs",
        "local-first API",
        "frontend chessData API",
        "frontend chess features",
        "chess video downstream",
    }
    assert required <= concepts


def test_all_target_architecture_owners_exist() -> None:
    assert missing_owner_paths() == []


def test_no_diagram_only_analysis_folder() -> None:
    assert "backend/modules/chess_intelligence/analysis" in DO_NOT_CREATE_FOR_DIAGRAM_ONLY
    assert forbidden_diagram_only_folders_present() == []
