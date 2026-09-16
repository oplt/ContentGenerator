"""Enqueue / process chess catalog Celery jobs (Phase 24)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.catalog_job_models import (
    ChessCatalogJob,
    ChessCatalogJobKind,
    ChessCatalogJobStatus,
)
from backend.modules.chess_intelligence.catalog_job_runners import run_catalog_job_body

logger = logging.getLogger(__name__)

_ALLOWED_KINDS = {k.value for k in ChessCatalogJobKind}


class ChessCatalogJobService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        kind: str,
        params: dict[str, Any],
        import_batch_id: str | None = None,
    ) -> ChessCatalogJob:
        if kind not in _ALLOWED_KINDS:
            raise HTTPException(status_code=422, detail=f"Unknown job kind: {kind}")
        self._validate_params(kind, params)
        batch = import_batch_id or str(uuid.uuid4())
        job = ChessCatalogJob(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            kind=kind,
            status=ChessCatalogJobStatus.QUEUED.value,
            progress=0.0,
            params=dict(params),
            result={},
            import_batch_id=batch,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    def enqueue_celery(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        from backend.workers.tasks import run_chess_catalog_job_task

        run_chess_catalog_job_task.delay(tenant_id=str(tenant_id), job_id=str(job_id))

    async def get_job(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessCatalogJob:
        result = await self.db.execute(
            select(ChessCatalogJob).where(
                ChessCatalogJob.id == job_id,
                ChessCatalogJob.tenant_id == tenant_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Catalog job not found")
        return job

    async def process_job(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID, celery_task_id: str | None = None
    ) -> ChessCatalogJob:
        job = await self.get_job(tenant_id=tenant_id, job_id=job_id)
        if job.status == ChessCatalogJobStatus.COMPLETED.value:
            return job
        if job.status == ChessCatalogJobStatus.CANCELLED.value:
            return job

        job.status = ChessCatalogJobStatus.RUNNING.value
        job.progress = 0.05
        job.error_message = None
        if celery_task_id:
            job.celery_task_id = celery_task_id
        await self.db.flush()

        try:
            result = await run_catalog_job_body(self.db, job)
            job.result = result
            job.progress = 1.0
            job.status = ChessCatalogJobStatus.COMPLETED.value
            job.error_message = None
        except Exception as exc:  # noqa: BLE001 — persist failure; caller may retry new job
            logger.exception("chess_catalog_job_failed job=%s kind=%s", job_id, job.kind)
            job.status = ChessCatalogJobStatus.FAILED.value
            job.error_message = str(exc)[:2000]
        await self.db.flush()
        return job

    def _validate_params(self, kind: str, params: dict[str, Any]) -> None:
        if kind in {
            ChessCatalogJobKind.PGN_IMPORT.value,
            ChessCatalogJobKind.PUZZLE_IMPORT.value,
        }:
            path = str(params.get("file_path") or "").strip()
            if not path:
                raise HTTPException(status_code=422, detail="params.file_path required")
        if kind == ChessCatalogJobKind.EXTRACT_CRITICAL_MOMENTS.value:
            if not params.get("analysis_job_id"):
                raise HTTPException(
                    status_code=422, detail="params.analysis_job_id required"
                )
        if kind == ChessCatalogJobKind.PROVIDER_SYNC.value:
            provider = str(params.get("provider") or "").strip()
            if provider not in {"lichess_masters", "chesscom"}:
                raise HTTPException(
                    status_code=422,
                    detail="params.provider must be lichess_masters or chesscom",
                )
            if provider == "chesscom" and not str(params.get("player") or "").strip():
                raise HTTPException(
                    status_code=422, detail="params.player required for chesscom sync"
                )
