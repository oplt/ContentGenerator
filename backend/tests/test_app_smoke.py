"""API smoke tests — app import and OpenAPI surface without live DB/Redis."""

from __future__ import annotations

REQUIRED_PATH_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/users",
    "/api/v1/sources",
    "/api/v1/stories",
    "/api/v1/content",
    "/api/v1/briefs",
    "/api/v1/approvals",
    "/api/v1/publishing",
    "/api/v1/analytics",
    "/api/v1/settings",
    "/api/v1/audit",
    "/api/v1/trending-repos",
    "/api/v1/chess-videos",
    "/api/v1/health",
)


def test_app_imports() -> None:
    from backend.api.main import app

    assert app.title
    assert app.version == "0.1.0"


def test_openapi_includes_core_routes() -> None:
    from backend.api.main import app

    schema = app.openapi()
    paths = schema.get("paths", {})
    assert paths, "OpenAPI schema must expose paths"

    for prefix in REQUIRED_PATH_PREFIXES:
        assert any(path.startswith(prefix) for path in paths), f"missing routes under {prefix}"
