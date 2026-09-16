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

CHESS_TABLES = (
    "chess_games",
    "chess_puzzles",
    "chess_game_sources",
    "chess_analysis_jobs",
    "chess_position_analyses",
    "chess_critical_moments",
    "chess_tactical_patterns",
    "chess_content_opportunity_scores",
    "chess_catalog_jobs",
    "chess_video_jobs",
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
    missing_chess = [name for name in CHESS_TABLES if name not in tables]
    assert not missing_chess, f"missing chess tables: {missing_chess}"


@pytest.mark.integration
def test_chess_tables_exist_after_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 23: chess vertical tables come from Alembic, not create_all."""
    import os

    if os.environ.get("CG_RUN_DB_MIGRATIONS") != "1":
        pytest.skip("set CG_RUN_DB_MIGRATIONS=1 with disposable Postgres to run")

    from alembic import command
    from sqlalchemy import create_engine, inspect, text

    from backend.core.config import settings

    cfg = _migration_config(monkeypatch)
    command.upgrade(cfg, "head")
    tables = _table_names_after_upgrade(cfg)
    missing = [name for name in CHESS_TABLES if name not in tables]
    assert not missing, f"missing chess tables: {missing}"

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    try:
        insp = inspect(engine)
        game_indexes = {ix["name"] for ix in insp.get_indexes("chess_games")}
        assert "uq_chess_games_tenant_id_game_fingerprint" in game_indexes
        assert "uq_chess_games_tenant_provider_external" in game_indexes
        puzzle_indexes = {ix["name"] for ix in insp.get_indexes("chess_puzzles")}
        assert "uq_chess_puzzles_tenant_id_puzzle_fingerprint" in puzzle_indexes
        assert "uq_chess_puzzles_tenant_provider_external" in puzzle_indexes
        fks = {fk["name"] for fk in insp.get_foreign_keys("chess_video_jobs")}
        assert "fk_chess_video_jobs_chess_game_id" in fks
        # Soft-delete partial unique: re-import after soft-delete must be allowed.
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT indexdef FROM pg_indexes
                    WHERE tablename = 'chess_games'
                      AND indexname = 'uq_chess_games_tenant_id_game_fingerprint'
                    """
                )
            ).scalar_one()
        assert "deleted_at IS NULL" in row
    finally:
        engine.dispose()


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
