"""§36 — chess v1 must not grow Kafka / ES / microservice / data-lake deps."""

from __future__ import annotations

import re
from pathlib import Path

from backend.modules.chess_intelligence.scope_v1 import (
    FORBIDDEN_V1_INFRA,
    PREFERRED_STACK,
    chess_v1_stays_modular_monolith,
    forbidden_infra_tokens,
)

REPO = Path(__file__).resolve().parents[2]
CHESS_ROOTS = (
    REPO / "backend" / "modules" / "chess_intelligence",
    REPO / "backend" / "modules" / "chess_video",
    REPO / "backend" / "workers" / "task_defs",
)
# Only chess-named worker tasks.
CHESS_WORKER_FILES = (
    "chess_analysis.py",
    "chess_catalog.py",
    "chess_video.py",
)

_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)",
    re.MULTILINE,
)


def test_scope_v1_contract() -> None:
    assert chess_v1_stays_modular_monolith() is True
    assert forbidden_infra_tokens() == FORBIDDEN_V1_INFRA
    assert "PostgreSQL" in PREFERRED_STACK
    assert "existing Celery" in PREFERRED_STACK
    assert "kafka" in FORBIDDEN_V1_INFRA
    assert "elasticsearch" in FORBIDDEN_V1_INFRA


def test_chess_packages_do_not_import_forbidden_infra() -> None:
    hits: list[str] = []
    files: list[Path] = []
    for root in CHESS_ROOTS[:2]:
        files.extend(root.rglob("*.py"))
    workers = REPO / "backend" / "workers" / "task_defs"
    for name in CHESS_WORKER_FILES:
        path = workers / name
        if path.is_file():
            files.append(path)

    for path in files:
        # Contract file names forbidden tokens as the deny-list itself.
        if path.name == "scope_v1.py":
            continue
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT_RE.finditer(text):
            mod = match.group(1).split(".")[0].lower()
            if mod in FORBIDDEN_V1_INFRA:
                hits.append(f"{path.relative_to(REPO)}:{mod}")
        lowered = text.lower()
        # Soft ban on obvious infra strings outside comments about forbidding them.
        for token in ("aiokafka", "confluent_kafka", "opensearchpy", "clickhouse_connect"):
            if token in lowered:
                hits.append(f"{path.relative_to(REPO)}:{token}")
    assert hits == [], f"forbidden infra in chess packages: {hits}"


def test_no_separate_chess_microservice_package() -> None:
    backend_modules = REPO / "backend" / "modules"
    names = {p.name for p in backend_modules.iterdir() if p.is_dir()}
    assert "chess_intelligence" in names
    assert "chess_video" in names
    # No parallel service package invented for hybrid chess.
    assert "chess_service" not in names
    assert "chess_microservice" not in names
    assert "chess_lake" not in names
