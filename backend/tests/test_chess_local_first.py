"""Local-first user-facing reads (§9) — GETs must not call live providers."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.modules.chess_intelligence import local_first
from backend.modules.chess_intelligence import service as catalog_service
from backend.modules.chess_intelligence.router import router


def test_local_first_get_paths_cover_catalog_reads() -> None:
    expected = {
        "/games",
        "/games/famous",
        "/games/{game_id}",
        "/games/{game_id}/moves",
        "/games/{game_id}/analysis",
        "/games/{game_id}/analyses",
        "/games/{game_id}/content-score",
        "/analysis/{job_id}",
        "/puzzles",
        "/puzzles/daily",
        "/puzzles/{puzzle_id}",
    }
    assert expected <= local_first.LOCAL_FIRST_GET_PATHS


def test_get_daily_puzzle_method_never_instantiates_provider() -> None:
    src = Path(catalog_service.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    method: ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ChessCatalogService":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "get_daily_puzzle":
                    method = item
                    break
    assert method is not None
    body_src = ast.get_source_segment(src, method) or ""
    assert "LichessPuzzlesProvider" not in body_src
    assert "get_puzzle_provider" not in body_src
    assert "provider.get_" not in body_src


def test_router_registers_daily_refresh_separate_from_get() -> None:
    methods_by_path: dict[str, set[str]] = {}
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or not methods:
            continue
        methods_by_path.setdefault(path, set()).update(methods)
    assert "GET" in methods_by_path["/puzzles/daily"]
    assert "POST" in methods_by_path["/puzzles/daily/refresh"]
    assert "POST" not in methods_by_path.get("/puzzles/daily", set())
