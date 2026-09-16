"""Phase 27 — chess_intelligence backend structure matches conventions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "modules" / "chess_intelligence"
WORKERS = Path(__file__).resolve().parents[1] / "workers" / "task_defs"

# Prompt Phase 27 suggested paths — must remain (direction adopted).
REQUIRED_PATHS = (
    "__init__.py",
    "models.py",
    "schemas.py",
    "repository.py",
    "service.py",
    "router.py",
    "normalizer.py",
    "fingerprint.py",
    "providers/__init__.py",
    "providers/base.py",
    "providers/lichess_masters.py",
    "providers/lichess_puzzles.py",
    "providers/chesscom.py",
    "importers/__init__.py",
    "importers/pgn_archive.py",
    "importers/lichess_puzzles.py",
    "engine/__init__.py",
    "engine/base.py",
    "engine/stockfish.py",
    "engine/analyzer.py",
    "engine/critical_moments.py",
    "data/famous_games.yaml",
)

# Extensions kept at module root / workers (platform convention).
REQUIRED_EXTENSIONS = (
    "catalog_queries.py",
    "dedupe.py",
    "source_rules.py",
    "analysis_service.py",
    "provenance_router.py",
    "catalog_job_service.py",
    "observability.py",
    "providers/provider_cache.py",
    "providers/http_errors.py",
    "engine/scores.py",
)

REQUIRED_WORKER_TASKS = (
    "chess_analysis.py",
    "chess_catalog.py",
    "chess_video.py",
)


def test_phase27_suggested_paths_exist() -> None:
    missing = [rel for rel in REQUIRED_PATHS if not (ROOT / rel).is_file()]
    assert not missing, f"missing Phase 27 core paths: {missing}"


def test_phase27_convention_extensions_exist() -> None:
    missing = [rel for rel in REQUIRED_EXTENSIONS if not (ROOT / rel).is_file()]
    assert not missing, f"missing adopted extensions: {missing}"


def test_celery_tasks_stay_in_workers_not_domain() -> None:
    for name in REQUIRED_WORKER_TASKS:
        assert (WORKERS / name).is_file(), f"missing worker task {name}"
    # Domain package must not grow Celery decorators.
    offenders: list[str] = []
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "@celery_app.task" in text or "celery_app.task(" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"Celery tasks leaked into domain: {offenders}"
