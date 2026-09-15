"""Guards that keep dormant feature modules out of the live API and schema."""

from __future__ import annotations

from pathlib import Path

from backend.core.dormant_modules import (
    DORMANT_MODULES,
    DORMANT_PACKAGE_NAMES,
    DORMANT_TABLE_NAMES,
    FORBIDDEN_OPENAPI_PREFIXES,
    LEGACY_LIVE_PACKAGE_PATHS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def test_dormant_registry_is_complete() -> None:
    expected = {"platform", "projects", "profile", "notifications", "calendar", "admin"}
    assert DORMANT_PACKAGE_NAMES == expected
    assert all(module.decision == "quarantine" for module in DORMANT_MODULES)
    for module in DORMANT_MODULES:
        assert module.package.startswith("backend.modules._dormant.")
        assert module.reason
        assert module.blockers


def test_legacy_live_dormant_paths_removed() -> None:
    for relative in LEGACY_LIVE_PACKAGE_PATHS:
        path = REPO_ROOT / relative
        assert not path.exists(), f"dormant module must not remain at live path: {relative}"


def test_dormant_packages_exist_under_quarantine() -> None:
    for name in DORMANT_PACKAGE_NAMES:
        package_dir = BACKEND_ROOT / "modules" / "_dormant" / name
        assert package_dir.is_dir(), f"missing quarantined package: {package_dir}"
        assert (package_dir / "router.py").exists() or name == "admin"
        if name == "admin":
            assert (package_dir / "router.py").exists()


def test_model_registry_excludes_dormant_packages() -> None:
    registry = (BACKEND_ROOT / "db" / "model_registry.py").read_text(encoding="utf-8")
    for name in DORMANT_PACKAGE_NAMES:
        assert f"modules.{name}" not in registry
        assert f"_dormant.{name}" not in registry


def test_api_router_excludes_dormant_imports() -> None:
    router_source = (BACKEND_ROOT / "api" / "router.py").read_text(encoding="utf-8")
    assert "_dormant" not in router_source
    for name in DORMANT_PACKAGE_NAMES:
        assert f"modules.{name}" not in router_source


def test_openapi_excludes_dormant_prefixes() -> None:
    from backend.api.main import app

    paths = set(app.openapi().get("paths", {}))
    for prefix in FORBIDDEN_OPENAPI_PREFIXES:
        leaked = [path for path in paths if path == prefix or path.startswith(f"{prefix}/")]
        assert not leaked, f"dormant routes leaked under {prefix}: {leaked}"


def test_sqlalchemy_metadata_excludes_dormant_tables() -> None:
    import backend.db.model_registry  # noqa: F401
    from backend.db.base import Base

    live_tables = set(Base.metadata.tables)
    leaked = sorted(live_tables & DORMANT_TABLE_NAMES)
    assert not leaked, f"dormant tables registered in metadata: {leaked}"
