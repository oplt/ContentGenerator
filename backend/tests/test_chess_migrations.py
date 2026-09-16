"""Phase 23 / §27 — chess catalog schema is Alembic-owned (no create_all for prod)."""

from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.db import model_registry  # noqa: F401
from backend.db.base import Base
from backend.modules.chess_intelligence.schema_changes import (
    EXISTING_CHESS_TABLES_DO_NOT_RECREATE,
    HYBRID_SCHEMA_ADDITIONS,
    REQUIRED_HYBRID_CONSTRAINTS,
    hybrid_schema_complete,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND_ROOT / "alembic" / "versions"

# Tables introduced for the chess vertical (intelligence + video bridge FK target).
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
    "chess_provider_sync_states",
    "chess_video_jobs",
)

# Constraint / index names that must appear in Alembic SQL (offline guard).
REQUIRED_MIGRATION_TOKENS = (
    "uq_chess_games_tenant_id_game_fingerprint",
    "uq_chess_games_tenant_provider_external",
    "uq_chess_puzzles_tenant_id_puzzle_fingerprint",
    "uq_chess_puzzles_tenant_provider_external",
    "uq_chess_game_sources_tenant_provider_external",
    "uq_chess_position_analyses_job_ply",
    "fk_chess_video_jobs_chess_game_id",
    "ix_chess_games_tenant_id_created_at",
    "ix_chess_puzzles_tenant_id_import_batch",
    "ix_chess_analysis_jobs_tenant_game_created",
    "chess_critical_moments",
    "chess_tactical_patterns",
    "chess_content_opportunity_scores",
    "f2a3b4c5d6e8",  # Phase 23 fingerprint partial uniques
    "chess_catalog_jobs",
    "f3a4b5c6d7e9",
    "chess_provider_sync_states",
    "f4a5b6c7d8e9",
    "uq_chess_provider_sync_tenant_provider_key",
    "g5a6b7c8d9e0",
    "uq_chess_analysis_jobs_tenant_fingerprint_active",
    "analysis_fingerprint",
    "h6b7c8d9e0f1",
    "ix_chess_games_tenant_id_white_player",
    "ix_chess_games_tenant_id_game_date",
)

CHESS_MIGRATION_PREFIXES = (
    "e3f4a5b6c7d8",
    "e4f5a6b7c8d9",
    "e5f6a7b8c9d1",
    "f7a8b9c0d1e2",
    "f8a9b0c1d2e4",
    "f9a0b1c2d3e4",
    "f0a1b2c3d4e6",
    "f1a2b3c4d5e7",
    "f2a3b4c5d6e8",
    "f3a4b5c6d7e9",
    "f4a5b6c7d8e9",
    "g5a6b7c8d9e0",
    "h6b7c8d9e0f1",
    "b8c9d0e1f2a3",
    "c9d0e1f2a3b4",
)


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_chess_orm_tables_registered() -> None:
    live = set(Base.metadata.tables)
    missing = [name for name in CHESS_TABLES if name not in live]
    assert not missing, f"chess tables missing from metadata (register models): {missing}"


def test_chess_migrations_exist_in_chain() -> None:
    script = _script_dir()
    ids = {rev.revision for rev in script.walk_revisions()}
    missing = [rid for rid in CHESS_MIGRATION_PREFIXES if rid not in ids]
    assert not missing, f"missing chess Alembic revisions: {missing}"
    heads = script.get_heads()
    assert len(heads) == 1, f"expected single Alembic head, got {heads}"
    # Head must be Phase 23 revision or a descendant (walk tip→base includes f2).
    assert "f2a3b4c5d6e8" in ids
    assert heads == ["h6b7c8d9e0f1"]


def test_chess_constraint_tokens_present_in_migrations() -> None:
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in VERSIONS.glob("*.py"))
    missing = [token for token in REQUIRED_MIGRATION_TOKENS if token not in corpus]
    assert not missing, f"constraint/index tokens missing from Alembic versions: {missing}"


def test_chess_game_fingerprint_is_soft_delete_partial() -> None:
    """ORM must declare partial unique so soft-deleted rows can be re-imported."""
    table = Base.metadata.tables["chess_games"]
    indexes = {idx.name: idx for idx in table.indexes}
    assert "uq_chess_games_tenant_id_game_fingerprint" in indexes
    idx = indexes["uq_chess_games_tenant_id_game_fingerprint"]
    assert idx.unique is True
    # Dialect opts carry postgresql_where when present.
    where = (idx.dialect_options.get("postgresql") or {}).get("where")
    assert where is not None
    assert "deleted_at IS NULL" in str(where)


def test_section_27_hybrid_additions_present() -> None:
    assert hybrid_schema_complete() is True
    assert EXISTING_CHESS_TABLES_DO_NOT_RECREATE <= set(CHESS_TABLES)
    revisions = {row["revision"] for row in HYBRID_SCHEMA_ADDITIONS}
    assert revisions == {"f4a5b6c7d8e9", "g5a6b7c8d9e0", "h6b7c8d9e0f1"}
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in VERSIONS.glob("*.py"))
    for token in REQUIRED_HYBRID_CONSTRAINTS:
        assert token in corpus


def test_hybrid_migrations_have_upgrade_and_downgrade() -> None:
    for row in HYBRID_SCHEMA_ADDITIONS:
        path = next(VERSIONS.glob(f"{row['revision']}_*.py"))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        assert "upgrade" in names and "downgrade" in names, path.name
        text = path.read_text(encoding="utf-8")
        # Must not recreate core catalog tables.
        for table in ("chess_games", "chess_puzzles"):
            assert f'create_table(\n        "{table}"' not in text
            assert f'create_table("{table}"' not in text


def test_analysis_fingerprint_backfill_is_safe_for_existing_rows() -> None:
    path = VERSIONS / "g5a6b7c8d9e0_add_chess_analysis_fingerprint.py"
    text = path.read_text(encoding="utf-8")
    assert "UPDATE chess_analysis_jobs" in text
    assert "legacy:" in text
    assert "nullable=False" in text
    assert "postgresql_where" in text


def test_sync_state_separate_from_catalog_jobs() -> None:
    """Feed checkpoint is its own table — not stuffed into ChessCatalogJob.result."""
    assert "chess_provider_sync_states" in Base.metadata.tables
    assert "chess_catalog_jobs" in Base.metadata.tables
    sync_cols = {c.name for c in Base.metadata.tables["chess_provider_sync_states"].columns}
    assert "high_water_mark" in sync_cols
    assert "cursor" in sync_cols
    job_cols = {c.name for c in Base.metadata.tables["chess_catalog_jobs"].columns}
    assert "high_water_mark" not in job_cols
