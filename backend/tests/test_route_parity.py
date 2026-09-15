"""Phase 8 — OpenAPI ↔ frontend parity inventory completeness."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "frontend" / "src" / "api" / "parityInventory.ts"


def _openapi_operations() -> set[tuple[str, str]]:
    from backend.api.main import app

    ops: set[tuple[str, str]] = set()
    for path, methods in app.openapi().get("paths", {}).items():
        for method in methods:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                ops.add((method.upper(), path))
    return ops


def _manifest_operations() -> set[tuple[str, str]]:
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    ops: set[tuple[str, str]] = set()
    for method, path in re.findall(
        r'method:\s*"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)",\s*path:\s*"([^"]+)"',
        text,
    ):
        ops.add((method, path))
    return ops


def test_openapi_stories_present_trends_not_duplicated() -> None:
    from backend.api.main import app

    paths = set(app.openapi().get("paths", {}))
    assert any(path.startswith("/api/v1/stories") for path in paths)
    assert "/api/v1/trends/clusters" not in paths
    assert "/api/v1/trends/trends/dashboard" not in paths


def test_legacy_trends_alias_registered() -> None:
    from backend.api.main import app

    routes = {getattr(route, "path", "") for route in app.routes}
    assert any(path.endswith("/trends/{path:path}") or "/trends/{path:path}" in path for path in routes) or any(
        "trends" in path and "{path" in path for path in routes
    )


def test_parity_inventory_matches_openapi_exactly() -> None:
    openapi = _openapi_operations()
    manifest = _manifest_operations()
    missing = sorted(f"{m} {p}" for m, p in (openapi - manifest))
    extra = sorted(f"{m} {p}" for m, p in (manifest - openapi))
    assert not missing, f"OpenAPI ops missing from parityInventory.ts: {missing}"
    assert not extra, f"parityInventory.ts ops not in OpenAPI: {extra}"
    assert len(manifest) >= 80


def test_mfa_and_parity_endpoints_in_openapi() -> None:
    paths = {path for _, path in _openapi_operations()}
    required = {
        "/api/v1/auth/mfa/enable",
        "/api/v1/auth/mfa/verify",
        "/api/v1/auth/mfa/disable",
        "/api/v1/users/me",
        "/api/v1/briefs/{brief_id}/rewrite",
        "/api/v1/briefs/{brief_id}/send-telegram",
        "/api/v1/content/asset-groups/{asset_group_id}/regenerate",
        "/api/v1/stories/candidates/{candidate_id}",
    }
    missing = required - paths
    assert not missing, f"missing OpenAPI paths: {sorted(missing)}"


def test_parity_inventory_file_present() -> None:
    assert INVENTORY_PATH.is_file()
    assert "PARITY_OPERATIONS" in INVENTORY_PATH.read_text(encoding="utf-8")
