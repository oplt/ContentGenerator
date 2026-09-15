"""T5.1 — route inventory: stories canonical; /trends is deprecation shim only."""

from __future__ import annotations


def test_openapi_stories_present_trends_not_duplicated() -> None:
    from backend.api.main import app

    paths = set(app.openapi().get("paths", {}))
    assert any(path.startswith("/api/v1/stories") for path in paths)
    # Full story router must not also be mounted under /trends (no /trends/clusters duplicate).
    assert "/api/v1/trends/clusters" not in paths
    assert "/api/v1/trends/trends/dashboard" not in paths


def test_legacy_trends_alias_registered() -> None:
    from backend.api.main import app

    routes = {getattr(route, "path", "") for route in app.routes}
    assert any(path.endswith("/trends/{path:path}") or "/trends/{path:path}" in path for path in routes) or any(
        "trends" in path and "{path" in path for path in routes
    )


def test_mfa_and_parity_endpoints_in_openapi() -> None:
    from backend.api.main import app

    paths = set(app.openapi().get("paths", {}))
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
