"""Phase 23 — chess catalog schema is Alembic-owned (no create_all for prod)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.db import model_registry  # noqa: F401
from backend.db.base import Base

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
