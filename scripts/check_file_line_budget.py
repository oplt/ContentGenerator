#!/usr/bin/env python3
"""Phase 10 — production source line-budget audit (≤300 lines).

Fails when a normal production source file exceeds LINE_BUDGET unless the path
matches an explicit exemption pattern.

Exemptions are only for generated, historical, lockfile, dormant, or test trees —
not for “temporarily large” production modules.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINE_BUDGET = 300

REPO_ROOT = Path(__file__).resolve().parents[1]

# Relative to repo root. Intentionally narrow.
EXEMPT_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^backend/alembic/versions/"),
    re.compile(r"^backend/modules/_dormant/"),
    re.compile(r"^backend/\.venv/"),
    re.compile(r"^frontend/node_modules/"),
    re.compile(r"^frontend/dist/"),
    re.compile(r"^frontend/playwright-report/"),
    re.compile(r"^frontend/test-results/"),
    re.compile(r"^frontend/blob-report/"),
    re.compile(r"^backend/tests/"),
    re.compile(r"^frontend/e2e/"),
    re.compile(r"^frontend/src/.+\.test\.(ts|tsx)$"),
    re.compile(r"^backend/.+/.*_test\.py$"),
    # Generated / lock artifacts (rarely scanned, but keep explicit).
    re.compile(r"(^|/)package-lock\.json$"),
    re.compile(r"(^|/)\.tsbuildinfo$"),
)

SCAN_GLOBS = (
    "backend/**/*.py",
    "frontend/src/**/*.ts",
    "frontend/src/**/*.tsx",
)


def _is_exempt(rel: str) -> bool:
    return any(pattern.search(rel) for pattern in EXEMPT_PATH_PATTERNS)


def _iter_production_sources() -> list[Path]:
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if _is_exempt(rel):
                continue
            # Skip caches / bytecode
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            files.append(path)
    return sorted(set(files))


def _line_count(path: Path) -> int:
    # Count physical lines (including blanks/comments) — matches `wc -l`.
    text = path.read_text(encoding="utf-8")
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def audit(*, budget: int = LINE_BUDGET) -> list[tuple[str, int]]:
    violations: list[tuple[str, int]] = []
    for path in _iter_production_sources():
        count = _line_count(path)
        if count > budget:
            violations.append((path.relative_to(REPO_ROOT).as_posix(), count))
    violations.sort(key=lambda item: (-item[1], item[0]))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=int, default=LINE_BUDGET)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON violations on stdout.",
    )
    args = parser.parse_args(argv)

    violations = audit(budget=args.budget)
    if args.json:
        import json

        print(json.dumps({"budget": args.budget, "violations": violations}, indent=2))
    elif violations:
        print(f"Line-budget violations (>{args.budget} lines):", file=sys.stderr)
        for rel, count in violations:
            print(f"  {count:4d}  {rel}", file=sys.stderr)
        print(
            f"\n{len(violations)} file(s) over budget. Split by responsibility "
            f"(see prompt Phase 10 / AGENTS.md).",
            file=sys.stderr,
        )
        return 1

    print(f"line-budget OK (≤{args.budget} lines, {len(_iter_production_sources())} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
