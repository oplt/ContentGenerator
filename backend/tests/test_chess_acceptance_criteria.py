"""§39 — critical acceptance criteria all present with evidence owners."""

from __future__ import annotations

from pathlib import Path

from backend.modules.chess_intelligence.acceptance_criteria import (
    ACCEPTANCE_CRITERIA,
    PROMPT_STATEMENTS,
    acceptance_ids,
    all_criteria_met_contract,
)

REPO = Path(__file__).resolve().parents[2]

# Exact prompt §39 checklist (normalized).
REQUIRED_STATEMENTS = (
    "local DB is operational source of truth",
    "historical games are not routinely re-downloaded",
    "recent games use incremental provider synchronization",
    "sync position survives process restarts",
    "failed syncs do not corrupt the checkpoint",
    "same game from multiple sources creates one canonical game",
    "all sources remain attributable",
    "famous status remains curation, not another PGN copy",
    "recent/notable is distinct from famous",
    "content opportunity is distinct from both",
    "normal GET endpoints do not require provider availability",
    "daily puzzle is locally persisted before being served",
    "provider outage has a sensible stale-data fallback",
    "equivalent Stockfish analysis is reused",
    "engine/configuration changes can create a new analysis",
    "concurrent identical analysis requests cannot duplicate work",
    "existing chess-video renderer remains the downstream renderer",
    "manual PGN/SAN/UCI video creation remains functional",
    "frontend never contains provider credentials",
    "no new scheduler/task system is introduced unnecessarily",
    "no duplicate canonical chess subsystem is created",
)


def test_acceptance_criteria_count_and_ids() -> None:
    assert all_criteria_met_contract() is True
    assert acceptance_ids() == tuple(f"AC{i:02d}" for i in range(1, 22))


def test_acceptance_statements_match_prompt() -> None:
    assert PROMPT_STATEMENTS == REQUIRED_STATEMENTS


def test_acceptance_evidence_paths_exist() -> None:
    missing: list[str] = []
    for criterion in ACCEPTANCE_CRITERIA:
        assert criterion.evidence, criterion.id
        for rel in criterion.evidence:
            if not (REPO / rel).exists():
                missing.append(f"{criterion.id}:{rel}")
    assert missing == [], f"§39 evidence gaps: {missing}"
