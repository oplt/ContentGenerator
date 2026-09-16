"""§38 — P0→P4 priority bands map to existing owners."""

from __future__ import annotations

from pathlib import Path

from backend.modules.chess_intelligence.priority_order import (
    PRIORITY_ORDER,
    priority_ids,
)

REPO = Path(__file__).resolve().parents[2]


def test_priority_order_is_p0_to_p4() -> None:
    assert priority_ids() == ("P0", "P1", "P2", "P3", "P4")
    assert PRIORITY_ORDER[0].title == "Local-First Correctness"
    assert PRIORITY_ORDER[2].title == "Analysis Reuse"
    assert PRIORITY_ORDER[3].title.startswith("Recent Discovery")


def test_each_priority_has_work_items_exit_and_owners() -> None:
    for band in PRIORITY_ORDER:
        assert band.work_items, band.id
        assert band.exit_criteria.strip(), band.id
        assert band.owners, band.id


def test_priority_owner_paths_exist() -> None:
    missing: list[str] = []
    for band in PRIORITY_ORDER:
        for rel in band.owners:
            path = REPO / rel
            if not path.exists():
                missing.append(f"{band.id}:{rel}")
    assert missing == [], f"§38 owner gaps: {missing}"


def test_p0_exit_mentions_no_external_providers() -> None:
    p0 = PRIORITY_ORDER[0]
    assert "external providers" in p0.exit_criteria.lower()
    assert "local-first daily puzzle" in p0.work_items


def test_p3_exit_separates_famous() -> None:
    p3 = next(b for b in PRIORITY_ORDER if b.id == "P3")
    assert "famous" in p3.exit_criteria.lower()
