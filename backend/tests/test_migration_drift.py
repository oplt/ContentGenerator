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
