"""§37 — target architecture as responsibility map (not a forced directory rename).

Conceptual surfaces → existing owning modules. Do **not** create folders solely
to mirror the prompt diagram when current layout already expresses the same
boundaries cleanly (Phase 27 + hybrid extensions).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = MODULE_ROOT.parents[2]


@dataclass(frozen=True, slots=True)
class ArchitectureSurface:
    concept: str
    owners: tuple[str, ...]  # paths relative to repo root


# Prompt §37 tree → adopted SignalForge layout.
TARGET_SURFACES: tuple[ArchitectureSurface, ...] = (
    ArchitectureSurface(
        "canonical game/puzzle domain",
        (
            "backend/modules/chess_intelligence/models.py",
            "backend/modules/chess_intelligence/service.py",
            "backend/modules/chess_intelligence/repository.py",
            "backend/modules/chess_intelligence/normalizer.py",
        ),
    ),
    ArchitectureSurface(
        "providers/Lichess master discovery",
        ("backend/modules/chess_intelligence/providers/lichess_masters.py",),
    ),
    ArchitectureSurface(
        "providers/Lichess puzzle discovery",
        ("backend/modules/chess_intelligence/providers/lichess_puzzles.py",),
    ),
    ArchitectureSurface(
        "providers/other supported providers",
        (
            "backend/modules/chess_intelligence/providers/chesscom.py",
            "backend/modules/chess_intelligence/providers/registry.py",
        ),
    ),
    ArchitectureSurface(
        "importers/historical PGN archives",
        ("backend/modules/chess_intelligence/importers/pgn_archive.py",),
    ),
    ArchitectureSurface(
        "fingerprint + dedupe",
        (
            "backend/modules/chess_intelligence/fingerprint.py",
            "backend/modules/chess_intelligence/dedupe.py",
        ),
    ),
    ArchitectureSurface(
        "persistent provider sync state",
        ("backend/modules/chess_intelligence/provider_sync_state.py",),
    ),
    ArchitectureSurface(
        "famous curation",
        (
            "backend/modules/chess_intelligence/famous_catalog.py",
            "backend/modules/chess_intelligence/famous_service.py",
            "backend/modules/chess_intelligence/famous_policy.py",
            "backend/modules/chess_intelligence/data/famous_games.yaml",
        ),
    ),
    ArchitectureSurface(
        "analysis/versioned Stockfish results",
        (
            "backend/modules/chess_intelligence/analysis_service.py",
            "backend/modules/chess_intelligence/analysis_fingerprint.py",
            "backend/modules/chess_intelligence/engine/stockfish.py",
        ),
    ),
    ArchitectureSurface(
        "critical moments",
        ("backend/modules/chess_intelligence/engine/critical_moments.py",),
    ),
    ArchitectureSurface(
        "content opportunity",
        (
            "backend/modules/chess_intelligence/content_opportunity.py",
            "backend/modules/chess_intelligence/content_score_service.py",
        ),
    ),
    ArchitectureSurface(
        "catalog jobs",
        (
            "backend/modules/chess_intelligence/catalog_job_service.py",
            "backend/modules/chess_intelligence/catalog_job_runners.py",
            "backend/workers/task_defs/chess_catalog.py",
        ),
    ),
    ArchitectureSurface(
        "local-first API",
        (
            "backend/modules/chess_intelligence/local_first.py",
            "backend/modules/chess_intelligence/router.py",
        ),
    ),
    ArchitectureSurface(
        "frontend chessData API",
        ("frontend/src/api/chessData.ts",),
    ),
    ArchitectureSurface(
        "frontend chess features",
        ("frontend/src/features/chess",),
    ),
    ArchitectureSurface(
        "chess video downstream",
        ("backend/modules/chess_video",),
    ),
)


# Explicit non-goals for §37 purity renames.
DO_NOT_CREATE_FOR_DIAGRAM_ONLY: frozenset[str] = frozenset(
    {
        "backend/modules/chess_intelligence/analysis",  # use analysis_*.py + engine/
        "backend/modules/chess_service",
        "backend/modules/chess_microservice",
    }
)


def missing_owner_paths() -> list[str]:
    missing: list[str] = []
    for surface in TARGET_SURFACES:
        for rel in surface.owners:
            path = REPO_ROOT / rel
            if not path.exists():
                missing.append(f"{surface.concept}:{rel}")
    return missing


def forbidden_diagram_only_folders_present() -> list[str]:
    return [
        rel
        for rel in DO_NOT_CREATE_FOR_DIAGRAM_ONLY
        if (REPO_ROOT / rel).exists()
    ]
