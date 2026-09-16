"""§25 — browse GETs never start sync; admin ops use catalog jobs."""

from __future__ import annotations

import ast
from pathlib import Path

from backend.modules.chess_intelligence import admin_sync, local_first, service as catalog_service
from backend.modules.chess_intelligence.catalog_job_schemas import ChessCatalogJobKindLiteral
from backend.modules.chess_intelligence.router import router


def test_browse_gets_must_not_start_sync_contract() -> None:
    assert admin_sync.browse_gets_must_not_start_sync() is True
    assert admin_sync.BROWSE_GET_MUST_NOT_SYNC <= local_first.LOCAL_FIRST_GET_PATHS


def test_admin_sync_actions_map_to_existing_job_kinds() -> None:
    kinds = set(ChessCatalogJobKindLiteral.__args__)  # type: ignore[attr-defined]
    for action, target in admin_sync.ADMIN_SYNC_ACTIONS.items():
        if action == "reanalyze_stockfish":
            assert target == "analyze_chess_game"
            continue
        assert target in kinds, f"{action} → {target} missing from catalog kinds"


def test_list_games_never_calls_providers_or_sync() -> None:
    src = Path(catalog_service.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    method: ast.AsyncFunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ChessCatalogService":
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "list_games":
                    method = item
                    break
    assert method is not None
    body = ast.get_source_segment(src, method) or ""
    assert "get_historical_game_provider" not in body
    assert "provider_sync" not in body
    assert "ChessCatalogJob" not in body
    assert "enqueue" not in body


def test_games_get_route_is_get_only() -> None:
    methods_by_path: dict[str, set[str]] = {}
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or not methods:
            continue
        methods_by_path.setdefault(path, set()).update(methods)
    assert methods_by_path["/games"] == {"GET"}
    assert "POST" not in methods_by_path["/games"]
