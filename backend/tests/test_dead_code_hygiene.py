"""T7.3 — reject reintroduction of verified-dead modules and tracked artifacts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"

REMOVED_PATHS = (
    BACKEND_ROOT / "core" / "cache_decorator.py",
    FRONTEND_ROOT / "src" / "features" / "auth" / "authStore.ts",
    FRONTEND_ROOT / "src" / "pages" / "PublishingPage.tsx",
    FRONTEND_ROOT / "src" / "components" / "dashboard" / "SourceHealthTable.tsx",
)

FORBIDDEN_TRACKED_SUFFIXES = (
    "dump.rdb",
    ".tsbuildinfo",
)
FORBIDDEN_TRACKED_PREFIXES = (
    "frontend/playwright-report/",
    "frontend/test-results/",
    "frontend/blob-report/",
)


def test_removed_dead_code_paths_stay_gone() -> None:
    for path in REMOVED_PATHS:
        assert not path.exists(), f"dead code reintroduced: {path.relative_to(REPO_ROOT)}"


def test_list_due_jobs_removed_from_publishing_repository() -> None:
    source = (BACKEND_ROOT / "modules" / "publishing" / "repository.py").read_text(encoding="utf-8")
    assert "def list_due_jobs" not in source


def test_gitignore_covers_runtime_artifacts() -> None:
    root_ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    frontend_ignore = (FRONTEND_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dump.rdb" in root_ignore
    assert "playwright-report" in root_ignore or "playwright-report" in frontend_ignore
    assert "tsbuildinfo" in root_ignore or "tsbuildinfo" in frontend_ignore
