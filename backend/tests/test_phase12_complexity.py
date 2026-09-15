"""Phase 12 — keep worst backend hotspots under practical complexity budgets."""

from __future__ import annotations

from pathlib import Path

import pytest

radon = pytest.importorskip("radon")
from radon.complexity import cc_visit  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Soft budgets after Phase 12 extraction (not a global CC gate).
COMPLEXITY_BUDGETS: dict[str, tuple[str, int]] = {
    "modules/approvals/telegram_callbacks.py": ("handle_telegram_callback", 12),
    "modules/approvals/telegram_callback_intents.py": ("dispatch_intent", 12),
    "modules/publishing/job_executor.py": ("publish_job", 15),
    "modules/publishing/providers.py": ("get_provider", 6),
    "modules/content_generation/originality.py": ("measure_originality", 4),
}


def _cc_for(path: Path, name: str) -> int:
    blocks = cc_visit(path.read_text(encoding="utf-8"))
    matches = [b.complexity for b in blocks if b.name == name or b.name.endswith(f".{name}")]
    assert matches, f"function {name} not found in {path}"
    return max(matches)


@pytest.mark.parametrize("rel,spec", sorted(COMPLEXITY_BUDGETS.items()))
def test_phase12_hotspot_complexity_budgets(rel: str, spec: tuple[str, int]) -> None:
    name, budget = spec
    path = BACKEND_ROOT / rel
    assert path.is_file(), rel
    assert _cc_for(path, name) <= budget, f"{rel}:{name} exceeds CC budget {budget}"


def test_phase12_hotspot_files_within_line_budget() -> None:
    for rel in COMPLEXITY_BUDGETS:
        path = BACKEND_ROOT / rel
        lines = path.read_text(encoding="utf-8").count("\n") + 1
        assert lines <= 300, f"{rel} has {lines} lines"
