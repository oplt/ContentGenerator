"""Migration graph / metadata drift guards (T8.2). Offline — no live DB required."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.core.dormant_modules import DORMANT_TABLE_NAMES
from backend.db.base import Base
from backend.db import model_registry  # noqa: F401

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND_ROOT / "alembic" / "versions"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_alembic_has_single_head() -> None:
    script = _script_dir()
    heads = script.get_heads()
    assert len(heads) == 1, f"expected single Alembic head, got {heads}"


def test_alembic_revision_chain_is_connected() -> None:
    script = _script_dir()
    revisions = list(script.walk_revisions())
    assert revisions, "no Alembic revisions found"
    # walk_revisions yields tip → base; every down_revision (except base) must exist.
    ids = {rev.revision for rev in revisions}
    for rev in revisions:
        down = rev.down_revision
        if down is None:
            continue
        if isinstance(down, tuple):
            for item in down:
                assert item in ids, f"missing parent {item} for {rev.revision}"
        else:
            assert down in ids, f"missing parent {down} for {rev.revision}"


def test_metadata_excludes_dormant_tables() -> None:
    live = set(Base.metadata.tables)
    overlap = live & DORMANT_TABLE_NAMES
    assert not overlap, f"dormant tables registered in metadata: {sorted(overlap)}"


def test_versions_directory_only_contains_python_migrations() -> None:
    assert VERSIONS.is_dir()
    for path in VERSIONS.iterdir():
        if path.name.startswith(".") or path.name == "__pycache__":
            continue
        assert path.suffix == ".py", f"unexpected non-migration file {path.name}"


@pytest.mark.integration
def test_alembic_upgrade_head_on_disposable_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Requires DATABASE_URL pointing at empty disposable Postgres (CI service).
    Skipped automatically when CG_RUN_DB_MIGRATIONS is unset.
    """
    import os

    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1":
        pytest.skip("set CG_RUN_DB_MIGRATIONS=1 with disposable Postgres to run")

    from alembic import command

    # Force null pool for one-shot migration process.
    monkeypatch.setenv("DB_POOL_USE_NULL", "true")
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")


WORKFLOW_TABLES = (
    "workflow_definitions",
    "workflow_versions",
    "automations",
    "automation_targets",
    "automation_occurrences",
    "workflow_runs",
    "workflow_node_runs",
    "brand_social_accounts",
)


def _migration_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setenv("DB_POOL_USE_NULL", "true")
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _table_names_after_upgrade(cfg: Config) -> set[str]:
    from sqlalchemy import create_engine, inspect

    from backend.core.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.integration
def test_alembic_upgrade_from_previous_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upgrade from parent revision, then to head (simulates existing deployments)."""
    import os

    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1":
        pytest.skip("set CG_RUN_DB_MIGRATIONS=1 with disposable Postgres to run")

    from alembic import command

    cfg = _migration_config(monkeypatch)
    script = _script_dir()
    head = script.get_heads()[0]
    parent = script.get_revision(head).down_revision
    assert isinstance(parent, str)

    command.upgrade(cfg, parent)
    tables = _table_names_after_upgrade(cfg)
    for name in WORKFLOW_TABLES:
        assert name in tables, f"missing {name} after upgrade to {parent}"

    command.upgrade(cfg, "head")
    tables_head = _table_names_after_upgrade(cfg)
    for name in WORKFLOW_TABLES:
        assert name in tables_head


@pytest.mark.integration
def test_workflow_tables_exist_after_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1":
        pytest.skip("set CG_RUN_DB_MIGRATIONS=1 with disposable Postgres to run")

    from alembic import command

    cfg = _migration_config(monkeypatch)
    command.upgrade(cfg, "head")
    tables = _table_names_after_upgrade(cfg)
    missing = [name for name in WORKFLOW_TABLES if name not in tables]
    assert not missing, f"missing workflow tables: {missing}"


# First workflow-domain Alembic revision (parent is last pre-workflow revision).
WORKFLOW_FOUNDATION_REVISION = "d0e1f2a3b4c5"
PRE_WORKFLOW_REVISION = "c9d0e1f2a3b4"


@pytest.mark.integration
def test_alembic_workflow_migrations_downgrade_and_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 0: disposable Postgres can downgrade workflow stack and return to head."""
    import os

    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1":
        pytest.skip("set CG_RUN_DB_MIGRATIONS=1 with disposable Postgres to run")

    from alembic import command

    cfg = _migration_config(monkeypatch)
    script = _script_dir()
    head = script.get_heads()[0]
    foundation = script.get_revision(WORKFLOW_FOUNDATION_REVISION)
    assert foundation is not None
    assert foundation.down_revision == PRE_WORKFLOW_REVISION

    command.upgrade(cfg, "head")
    tables_head = _table_names_after_upgrade(cfg)
    for name in WORKFLOW_TABLES:
        assert name in tables_head

    command.downgrade(cfg, PRE_WORKFLOW_REVISION)
    tables_pre = _table_names_after_upgrade(cfg)
    for name in WORKFLOW_TABLES:
        assert name not in tables_pre, f"{name} should be dropped after downgrade"

    command.upgrade(cfg, "head")
    tables_restored = _table_names_after_upgrade(cfg)
    for name in WORKFLOW_TABLES:
        assert name in tables_restored
    assert head == script.get_heads()[0]
