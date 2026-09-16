"""Alembic revision gate — refuse work when DB is behind code head."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.core.config import settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class SchemaRevisionStatus:
    ok: bool
    current: str | None
    expected_heads: tuple[str, ...]
    detail: str

    def as_component(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "error",
            "current": self.current,
            "expected_heads": list(self.expected_heads),
            "detail": self.detail,
        }


class SchemaRevisionError(RuntimeError):
    """Database schema is not at the expected Alembic head."""


def alembic_script_directory() -> ScriptDirectory:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(cfg)


def expected_heads() -> tuple[str, ...]:
    return tuple(sorted(alembic_script_directory().get_heads()))


def _sync_engine() -> Engine:
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    return create_engine(url, pool_pre_ping=True)


def read_current_revision(engine: Engine | None = None) -> str | None:
    own = engine is None
    eng = engine or _sync_engine()
    try:
        with eng.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
            return str(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001 — surface as revision status
        raise SchemaRevisionError(f"cannot read alembic_version: {exc}") from exc
    finally:
        if own:
            eng.dispose()


def check_schema_revision(engine: Engine | None = None) -> SchemaRevisionStatus:
    heads = expected_heads()
    if not heads:
        return SchemaRevisionStatus(
            ok=False,
            current=None,
            expected_heads=(),
            detail="no Alembic heads found in repository",
        )
    try:
        current = read_current_revision(engine)
    except SchemaRevisionError as exc:
        return SchemaRevisionStatus(
            ok=False,
            current=None,
            expected_heads=heads,
            detail=str(exc),
        )
    if current is None:
        return SchemaRevisionStatus(
            ok=False,
            current=None,
            expected_heads=heads,
            detail="alembic_version is empty; run: make migrate",
        )
    if current not in heads:
        return SchemaRevisionStatus(
            ok=False,
            current=current,
            expected_heads=heads,
            detail=(
                f"database at {current}, code expects {', '.join(heads)}; "
                "run: make migrate (alembic upgrade head)"
            ),
        )
    return SchemaRevisionStatus(
        ok=True,
        current=current,
        expected_heads=heads,
        detail="schema at head",
    )


def assert_schema_at_head(*, role: str = "process") -> SchemaRevisionStatus:
    """Raise SchemaRevisionError when DB revision != Alembic head."""
    if not settings.SCHEMA_REVISION_ENFORCE:
        return SchemaRevisionStatus(
            ok=True,
            current=None,
            expected_heads=expected_heads(),
            detail="SCHEMA_REVISION_ENFORCE=false; skipped",
        )
    status = check_schema_revision()
    if not status.ok:
        raise SchemaRevisionError(f"{role}: {status.detail}")
    return status
