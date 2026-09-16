"""§35 — performance: local search, indexes, streaming, bounded sync, Stockfish off HTTP."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.db import model_registry  # noqa: F401 — register metadata
from backend.modules.chess_intelligence import local_first, performance
from backend.modules.chess_intelligence.importers import pgn_archive
from backend.modules.chess_intelligence.performance import (
    REQUIRED_INDEXES,
    historical_import_streams,
    orm_has_required_indexes,
    provider_sync_is_serial_per_game,
    required_index_names,
    stockfish_off_http_path,
)


ROOT = Path(__file__).resolve().parents[1] / "modules" / "chess_intelligence"


def test_performance_contract_flags() -> None:
    assert provider_sync_is_serial_per_game() is True
    assert historical_import_streams() is True
    assert stockfish_off_http_path() is True
    purposes = {i.purpose for i in REQUIRED_INDEXES}
    assert "canonical fingerprint" in purposes
    assert "players (white)" in purposes
    assert "game date" in purposes
    assert "sync-state identity" in purposes


def test_orm_declares_required_performance_indexes() -> None:
    missing = orm_has_required_indexes()
    assert missing == [], f"missing ORM indexes/constraints: {missing}"
    assert "ix_chess_games_tenant_id_white_player" in required_index_names()


def test_local_first_search_paths_cover_games_and_puzzles() -> None:
    assert "/games" in local_first.LOCAL_FIRST_GET_PATHS
    assert "/games/famous" in local_first.LOCAL_FIRST_GET_PATHS
    assert "/puzzles" in local_first.LOCAL_FIRST_GET_PATHS


def test_pgn_importer_streams_games() -> None:
    src = Path(pgn_archive.__file__).read_text(encoding="utf-8")
    assert "chess.pgn.read_game" in src
    assert "iter_pgn_games" in src
    # Must not load whole archive via Path.read_text into a single parse.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            body = ast.get_source_segment(src, node) or ""
            assert "read_text(" not in body
            assert "iter_pgn_file" in body


def test_provider_sync_does_not_gather_parallel_fetches() -> None:
    sync_src = (ROOT / "catalog_job_sync.py").read_text(encoding="utf-8")
    # Serial loop over batch; no asyncio.gather of get_game calls.
    assert "for i, summary in enumerate(batch)" in sync_src
    assert "asyncio.gather" not in sync_src


def test_analyze_http_enqueues_celery_not_process_job() -> None:
    router_src = (ROOT / "router.py").read_text(encoding="utf-8")
    tree = ast.parse(router_src)
    analyze: ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and "analyze" in node.name:
            analyze = node
            break
        if isinstance(node, ast.FunctionDef) and "analyze" in node.name:
            # decorated async may still be AsyncFunctionDef
            pass
    # Find via decorator path string in source instead.
    assert "enqueue_celery" in router_src
    assert "process_job(" not in router_src
    assert stockfish_off_http_path() is True
