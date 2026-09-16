"""Phase 24 — chess catalog Celery async jobs."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import cast
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import Table, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.db.base import Base
from backend.modules.chess_intelligence.catalog_job_models import (
    ChessCatalogJob,
    ChessCatalogJobKind,
    ChessCatalogJobStatus,
)
from backend.modules.chess_intelligence.catalog_job_service import ChessCatalogJobService
from backend.modules.chess_intelligence.importers.pgn_archive import ImportProgress
from backend.modules.identity_access.models import Tenant
from backend.workers.task_policy import TASK_POLICIES


_PGN = """
[Event "Test"]
[White "A"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0
"""


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk_on(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        # Keep FK off: User table omitted (sqlite create_all index issues).
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=cast(
                    list[Table],
                    [Tenant.__table__, ChessCatalogJob.__table__],
                ),
            )
        )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)()


def test_catalog_job_task_policy_registered() -> None:
    name = "backend.workers.tasks.run_chess_catalog_job_task"
    assert name in TASK_POLICIES
    assert TASK_POLICIES[name].acks_late is True
    assert TASK_POLICIES[name].workload == "io"


def test_analyze_chess_game_task_still_registered() -> None:
    assert "backend.workers.tasks.analyze_chess_game_task" in TASK_POLICIES


def test_enqueue_validates_params() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        svc = ChessCatalogJobService(db)
        try:
            await svc.enqueue(
                tenant_id=tenant_id,
                user_id=None,
                kind=ChessCatalogJobKind.PGN_IMPORT.value,
                params={},
            )
            raise AssertionError("expected 422")
        except HTTPException as exc:
            assert exc.status_code == 422
        await db.close()

    asyncio.run(_run())


def test_process_pgn_import_persists_progress(tmp_path: Path) -> None:
    async def _run() -> None:
        pgn_path = tmp_path / "games.pgn"
        pgn_path.write_text(_PGN, encoding="utf-8")
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        svc = ChessCatalogJobService(db)
        job = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            kind=ChessCatalogJobKind.PGN_IMPORT.value,
            params={
                "file_path": str(pgn_path),
                "provider": "pgn_archive",
                "dry_run": True,
                "batch_size": 1,
            },
        )
        await db.commit()

        progress = ImportProgress(scanned=1, inserted=1, batches_committed=1)

        async def _fake_run(self, config, *, on_batch=None):  # noqa: ANN001
            if on_batch:
                await on_batch(progress)
            return progress

        with patch(
            "backend.modules.chess_intelligence.catalog_job_runners.PgnArchiveImporter.run",
            _fake_run,
        ):
            done = await svc.process_job(tenant_id=tenant_id, job_id=job.id, celery_task_id="c1")

        assert done.status == ChessCatalogJobStatus.COMPLETED.value
        assert done.progress == 1.0
        assert done.result.get("inserted") == 1
        assert done.celery_task_id == "c1"

        # Idempotent re-run
        again = await svc.process_job(tenant_id=tenant_id, job_id=job.id)
        assert again.status == ChessCatalogJobStatus.COMPLETED.value
        await db.close()

    asyncio.run(_run())


def test_process_missing_file_marks_failed(tmp_path: Path) -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        svc = ChessCatalogJobService(db)
        job = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            kind=ChessCatalogJobKind.PUZZLE_IMPORT.value,
            params={"file_path": str(tmp_path / "missing.csv")},
        )
        await db.commit()
        done = await svc.process_job(tenant_id=tenant_id, job_id=job.id)
        assert done.status == ChessCatalogJobStatus.FAILED.value
        assert done.error_message
        row = (
            await db.execute(select(ChessCatalogJob).where(ChessCatalogJob.id == job.id))
        ).scalar_one()
        assert row.status == ChessCatalogJobStatus.FAILED.value
        await db.close()

    asyncio.run(_run())


def test_enrich_famous_kind_runs() -> None:
    async def _run() -> None:
        db = await _session()
        tenant_id = uuid.uuid4()
        db.add(Tenant(id=tenant_id, name="T", slug=f"t-{tenant_id.hex[:8]}"))
        await db.commit()
        svc = ChessCatalogJobService(db)
        job = await svc.enqueue(
            tenant_id=tenant_id,
            user_id=None,
            kind=ChessCatalogJobKind.ENRICH_FAMOUS.value,
            params={"dry_run": True, "limit": 10},
        )
        await db.commit()

        class _Report:
            scanned = 0
            matched = 0
            updated = 0
            skipped_low_score = 0

        async def _apply(self, **kwargs):  # noqa: ANN001, ANN003
            return _Report()

        with patch(
            "backend.modules.chess_intelligence.catalog_job_runners.FamousCatalogService.apply_to_tenant",
            _apply,
        ):
            done = await svc.process_job(tenant_id=tenant_id, job_id=job.id)
        assert done.status == ChessCatalogJobStatus.COMPLETED.value
        assert done.result["scanned"] == 0
        await db.close()

    asyncio.run(_run())
