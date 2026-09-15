"""Phase 10 — production file line-budget gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_file_line_budget.py"


def test_line_budget_script_exists() -> None:
    assert SCRIPT.is_file()


def test_line_budget_audit_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Production files exceed the 300-line budget.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
