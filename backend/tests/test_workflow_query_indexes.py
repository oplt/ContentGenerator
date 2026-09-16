"""Workflow query indexes (ops Phase 5)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_includes_workflow_query_indexes() -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["d2e3f4a5b6c7"]


def test_workflow_query_index_migration_ops() -> None:
    path = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "a3b4c5d6e7f8_workflow_query_indexes.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "ix_workflow_definitions_tenant_updated_at_alive" in text
    assert "ix_automations_tenant_updated_at_alive" in text
    assert "ix_automations_due_schedule_next_run_at" in text
    assert "ix_workflow_runs_tenant_id_created_at" in text
    assert "ix_workflow_definitions_tenant_id_enabled" in text  # dropped in upgrade
    assert "ix_automations_enabled_next_run_at" in text  # dropped in upgrade
    assert "trigger_type = 'schedule'" in text
