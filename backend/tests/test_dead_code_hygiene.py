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
    REPO_ROOT / "tasks.txt",
    FRONTEND_ROOT / ".codex",
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

# Phase 11: empty local agent scratch files must stay untracked.
FORBIDDEN_TRACKED_EXACT = (
    "tasks.txt",
    "frontend/.codex",
)


def test_removed_dead_code_paths_stay_gone() -> None:
    for path in REMOVED_PATHS:
        assert not path.exists(), f"dead code reintroduced: {path.relative_to(REPO_ROOT)}"


def test_zero_byte_scratch_artifacts_not_tracked() -> None:
    import subprocess

    tracked = subprocess.check_output(
        ["git", "ls-files", "--", *FORBIDDEN_TRACKED_EXACT],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()
    assert tracked == [], f"scratch artifacts re-tracked: {tracked}"


def test_list_due_jobs_removed_from_publishing_repository() -> None:
    source = (BACKEND_ROOT / "modules" / "publishing" / "repository.py").read_text(encoding="utf-8")
    assert "def list_due_jobs" not in source


def test_gitignore_covers_runtime_artifacts() -> None:
    root_ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    frontend_ignore = (FRONTEND_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dump.rdb" in root_ignore
    assert "playwright-report" in root_ignore or "playwright-report" in frontend_ignore
    assert "tsbuildinfo" in root_ignore or "tsbuildinfo" in frontend_ignore
    assert "tasks.txt" in root_ignore
    assert ".codex" in root_ignore or ".codex" in frontend_ignore
    assert "lichess_db_puzzle" in root_ignore


def test_backend_deps_exclude_proven_unused_packages() -> None:
    pyproject = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for dep in ("playwright", "faster-whisper", "numpy"):
        assert dep not in pyproject, f"unused dep still in pyproject: {dep}"
        assert dep not in requirements, f"unused dep still in requirements: {dep}"
