"""Chess video orchestration service."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.storage import object_storage
from backend.modules.chess_video.fingerprint import compute_render_fingerprint
from backend.modules.chess_video.models import ChessVideoJob, ChessVideoJobStatus
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input
from backend.modules.chess_video.pipeline import cleanup_pipeline, render_chess_video
from backend.modules.chess_video.presets import get_preset
from backend.modules.chess_video.renderer import RENDERER_VERSION
from backend.modules.chess_video.repository import ChessVideoRepository
from backend.modules.chess_video.schemas import (
    ChessVideoCreateRequest,
    ChessVideoValidateRequest,
    ChessVideoValidateResponse,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChessVideoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ChessVideoRepository(db)

    async def validate(self, payload: ChessVideoValidateRequest) -> ChessVideoValidateResponse:
        try:
            game = parse_chess_input(payload.source_text, payload.input_format)  # type: ignore[arg-type]
        except ChessParseError as exc:
            return ChessVideoValidateResponse(
                valid=False,
                input_format=payload.input_format,
                errors=[str(exc)],
            )
        return ChessVideoValidateResponse(
            valid=True,
            input_format=game.input_format,
            detected_format=game.input_format,
            normalized_pgn=game.normalized_pgn,
            white_player=game.white_player,
            black_player=game.black_player,
            event=game.event,
            game_date=game.date,
            result=game.result,
            starting_fen=game.starting_fen,
            move_count=game.move_count,
            errors=[],
        )

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        payload: ChessVideoCreateRequest,
    ) -> ChessVideoJob:
        try:
            game = parse_chess_input(payload.source_text, payload.input_format)  # type: ignore[arg-type]
            # Validate preset early.
            get_preset(payload.render_preset)
        except ChessParseError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        fingerprint = compute_render_fingerprint(
            normalized_pgn=game.normalized_pgn,
            starting_fen=game.starting_fen,
            orientation=payload.orientation,
            render_preset=payload.render_preset,
            seconds_per_move=payload.seconds_per_move,
            include_coordinates=payload.include_coordinates,
            include_move_text=payload.include_move_text,
            title=payload.title,
        )
        source_hash = hashlib.sha256(payload.source_text.encode("utf-8")).hexdigest()

        cached = await self.repo.find_reusable_completed(
            tenant_id=tenant_id, render_fingerprint=fingerprint
        )
        job = ChessVideoJob(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            status=ChessVideoJobStatus.QUEUED.value,
            stage=ChessVideoJobStatus.QUEUED.value,
            progress=0.0,
            input_format=game.input_format,
            source_text=payload.source_text,
            normalized_pgn=game.normalized_pgn,
            source_hash=source_hash,
            white_player=game.white_player,
            black_player=game.black_player,
            event=game.event,
            game_date=game.date,
            result=game.result,
            starting_fen=game.starting_fen,
            move_count=game.move_count,
            orientation=payload.orientation,
            render_preset=payload.render_preset,
            seconds_per_move=payload.seconds_per_move,
            include_coordinates=payload.include_coordinates,
            include_move_text=payload.include_move_text,
            title=payload.title,
            subtitle=payload.subtitle,
            renderer_version=RENDERER_VERSION,
            render_fingerprint=fingerprint,
        )

        if cached is not None and cached.video_public_url:
            self._copy_cached_outputs(job, cached)
            await self.repo.create(job)
            return job

        await self.repo.create(job)
        return job

    def enqueue_job(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        self._enqueue(tenant_id=tenant_id, job_id=job_id)

    async def get(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> ChessVideoJob:
        job = await self.repo.get_for_tenant(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chess video job not found")
        return job

    async def list(self, *, tenant_id: uuid.UUID, limit: int = 50) -> list[ChessVideoJob]:
        return list(await self.repo.list_for_tenant(tenant_id=tenant_id, limit=limit))

    async def retry(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> ChessVideoJob:
        job = await self.get(tenant_id=tenant_id, job_id=job_id)
        if job.status not in {
            ChessVideoJobStatus.FAILED.value,
            ChessVideoJobStatus.CANCELLED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only failed or cancelled jobs can be retried",
            )
        job.status = ChessVideoJobStatus.QUEUED.value
        job.stage = ChessVideoJobStatus.QUEUED.value
        job.progress = 0.0
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        await self.db.flush()
        return job

    async def delete(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, str | None]:
        """Hard-delete the job row (PGN/source_text included) and return storage cleanup keys."""
        job = await self.get(tenant_id=tenant_id, job_id=job_id)
        payload = {
            "tenant_id": str(tenant_id),
            "job_id": str(job_id),
            "video_key": job.video_storage_key,
            "thumb_key": job.thumbnail_storage_key,
        }
        await self.repo.delete(job)
        return payload

    @staticmethod
    async def cleanup_storage(*, cleanup: dict[str, str | None]) -> None:
        video_key = cleanup.get("video_key")
        thumb_key = cleanup.get("thumb_key")
        tenant_id = cleanup.get("tenant_id")
        job_id = cleanup.get("job_id")
        if video_key:
            await object_storage.delete_object(video_key)
        if thumb_key:
            await object_storage.delete_object(thumb_key)
        if tenant_id and job_id:
            await object_storage.delete_prefix(prefix=f"tenants/{tenant_id}/chess-videos/{job_id}")

    async def process_job(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> ChessVideoJob:
        job = await self.repo.get_for_tenant(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise ValueError(f"Chess video job {job_id} not found for tenant {tenant_id}")

        if (
            job.status == ChessVideoJobStatus.COMPLETED.value
            and job.video_public_url
        ):
            return job

        if job.render_fingerprint:
            cached = await self.repo.find_reusable_completed(
                tenant_id=tenant_id, render_fingerprint=job.render_fingerprint
            )
            if cached is not None and cached.id != job.id and cached.video_public_url:
                self._copy_cached_outputs(job, cached)
                await self.db.flush()
                return job

        artifacts = None
        try:
            job.started_at = job.started_at or _utcnow()
            await self._set_progress(job, ChessVideoJobStatus.VALIDATING, 0.10)
            game = parse_chess_input(job.source_text, job.input_format)  # type: ignore[arg-type]
            job.normalized_pgn = game.normalized_pgn
            job.white_player = game.white_player
            job.black_player = game.black_player
            job.event = game.event
            job.game_date = game.date
            job.result = game.result
            job.starting_fen = game.starting_fen
            job.move_count = game.move_count
            job.input_format = game.input_format

            await self._set_progress(job, ChessVideoJobStatus.PREPARING, 0.20)
            await self._set_progress(job, ChessVideoJobStatus.RENDERING, 0.40)

            artifacts = await asyncio.to_thread(
                render_chess_video,
                game,
                render_preset=job.render_preset,
                seconds_per_move=job.seconds_per_move,
                include_coordinates=job.include_coordinates,
                include_move_text=job.include_move_text,
                title=job.title,
            )

            await self._set_progress(job, ChessVideoJobStatus.ENCODING, 0.85)
            await self._set_progress(job, ChessVideoJobStatus.UPLOADING, 0.92)

            video_key = f"tenants/{tenant_id}/chess-videos/{job.id}/video.mp4"
            thumb_key = f"tenants/{tenant_id}/chess-videos/{job.id}/thumbnail.png"
            video_url = await object_storage.upload_file(
                object_key=video_key,
                file_path=artifacts.video.output_path,
                content_type="video/mp4",
            )
            thumb_url = await object_storage.upload_file(
                object_key=thumb_key,
                file_path=artifacts.thumbnail_path,
                content_type="image/png",
            )

            job.video_storage_key = video_key
            job.video_public_url = video_url
            job.thumbnail_storage_key = thumb_key
            job.thumbnail_public_url = thumb_url
            job.duration_seconds = artifacts.video.duration_seconds
            job.width = artifacts.video.width
            job.height = artifacts.video.height
            job.file_size_bytes = artifacts.video.file_size_bytes
            job.renderer_version = RENDERER_VERSION
            job.status = ChessVideoJobStatus.COMPLETED.value
            job.stage = ChessVideoJobStatus.COMPLETED.value
            job.progress = 1.0
            job.completed_at = _utcnow()
            job.error_message = None
            await self.db.flush()
            return job
        except Exception as exc:
            logger.exception("chess video job %s failed", job_id)
            # Durable failure must survive run_async_task's rollback-on-raise.
            await self.db.rollback()
            failed = await self.repo.get_for_tenant(tenant_id=tenant_id, job_id=job_id)
            if failed is not None:
                failed.status = ChessVideoJobStatus.FAILED.value
                failed.stage = ChessVideoJobStatus.FAILED.value
                failed.error_message = str(exc)[:2000]
                await self.db.commit()
            raise
        finally:
            cleanup_pipeline(artifacts)

    async def _set_progress(self, job: ChessVideoJob, stage: ChessVideoJobStatus, progress: float) -> None:
        job.status = stage.value
        job.stage = stage.value
        job.progress = progress
        # Commit so polling clients see stage/progress during long Pillow/FFmpeg work.
        await self.db.commit()

    @staticmethod
    def _copy_cached_outputs(job: ChessVideoJob, cached: ChessVideoJob) -> None:
        job.status = ChessVideoJobStatus.COMPLETED.value
        job.stage = ChessVideoJobStatus.COMPLETED.value
        job.progress = 1.0
        job.video_storage_key = cached.video_storage_key
        job.video_public_url = cached.video_public_url
        job.thumbnail_storage_key = cached.thumbnail_storage_key
        job.thumbnail_public_url = cached.thumbnail_public_url
        job.duration_seconds = cached.duration_seconds
        job.width = cached.width
        job.height = cached.height
        job.file_size_bytes = cached.file_size_bytes
        job.renderer_version = cached.renderer_version or RENDERER_VERSION
        job.completed_at = _utcnow()
        job.started_at = job.started_at or _utcnow()
        job.error_message = None

    @staticmethod
    def _enqueue(*, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        from backend.workers.tasks import generate_chess_video_task

        generate_chess_video_task.delay(tenant_id=str(tenant_id), job_id=str(job_id))
