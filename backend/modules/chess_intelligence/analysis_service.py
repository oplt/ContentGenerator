"""Enqueue and run Stockfish analysis jobs (engine work stays off HTTP)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.chess_intelligence.analysis_persist import persist_analysis_results
from backend.modules.chess_intelligence.catalog_queries import ChessCatalogQuery
from backend.modules.chess_intelligence.content_score_service import (
    latest_content_score as load_latest_content_score,
)
from backend.modules.chess_intelligence.engine.analyzer import analyze_game
from backend.modules.chess_intelligence.engine.base import ChessEngine
from backend.modules.chess_intelligence.engine.stockfish import (
    ChessEngineConfigError,
    open_stockfish,
)
from backend.modules.chess_intelligence.models import (
    ChessAnalysisJob,
    ChessAnalysisJobStatus,
    ChessContentOpportunityScore,
    ChessCriticalMoment,
    ChessPositionAnalysis,
    ChessTacticalPattern,
)
from backend.modules.chess_intelligence.observability import record_engine_analysis
from backend.modules.chess_intelligence.schemas import (
    ChessAnalysisJobResponse,
    ChessAnalysisRequest,
    ChessContentOpportunityScoreSchema,
    ChessCriticalMomentSchema,
    ChessPositionAnalysisSchema,
    ChessTacticalPatternSchema,
)
from backend.modules.chess_video.parser import ChessParseError, parse_chess_input

logger = logging.getLogger(__name__)

EngineFactory = Callable[[], ChessEngine]


class ChessAnalysisService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self.db = db
        self.queries = ChessCatalogQuery(db)
        self._engine_factory = engine_factory

    def _settings_payload(
        self, payload: ChessAnalysisRequest | None
    ) -> dict[str, Any]:
        depth = (
            payload.depth
            if payload and payload.depth is not None
            else settings.CHESS_ENGINE_DEPTH
        )
        time_limit = (
            payload.time_limit_seconds
            if payload and payload.time_limit_seconds is not None
            else settings.CHESS_ENGINE_TIME_LIMIT
        )
        return {
            "depth": depth,
            "time_limit_seconds": time_limit,
            "hash_mb": settings.CHESS_ENGINE_HASH_MB,
            "threads": settings.CHESS_ENGINE_THREADS,
            "score_perspective": "white",
        }

    async def enqueue(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        game_id: uuid.UUID,
        payload: ChessAnalysisRequest | None = None,
    ) -> ChessAnalysisJob:
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")
        if not settings.STOCKFISH_PATH.strip() and self._engine_factory is None:
            raise HTTPException(
                status_code=503,
                detail="Stockfish is not configured (set STOCKFISH_PATH)",
            )

        cfg = self._settings_payload(payload)
        job = ChessAnalysisJob(
            tenant_id=tenant_id,
            chess_game_id=game_id,
            created_by_user_id=user_id,
            status=ChessAnalysisJobStatus.QUEUED.value,
            depth=cfg["depth"],
            time_limit_seconds=cfg["time_limit_seconds"],
            hash_mb=cfg["hash_mb"],
            threads=cfg["threads"],
            analysis_settings=cfg,
            ply_count=game.move_count,
        )
        self.db.add(job)
        await self.db.flush()
        return job

    def enqueue_celery(self, *, tenant_id: uuid.UUID, job_id: uuid.UUID) -> None:
        from backend.workers.tasks import analyze_chess_game_task

        analyze_chess_game_task.delay(tenant_id=str(tenant_id), job_id=str(job_id))

    async def get_job(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessAnalysisJobResponse:
        job = await self._get_job_row(tenant_id=tenant_id, job_id=job_id)
        positions = await self._positions_for_job(job_id=job.id)
        moments = await self._moments_for_job(job_id=job.id)
        patterns = await self._patterns_for_job(job_id=job.id)
        content_score = await self._content_score_for_job(job_id=job.id)
        return self._to_response(job, positions, moments, patterns, content_score)

    async def latest_for_game(
        self, *, tenant_id: uuid.UUID, game_id: uuid.UUID
    ) -> ChessAnalysisJobResponse | None:
        result = await self.db.execute(
            select(ChessAnalysisJob)
            .where(
                ChessAnalysisJob.tenant_id == tenant_id,
                ChessAnalysisJob.chess_game_id == game_id,
            )
            .order_by(ChessAnalysisJob.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        positions = await self._positions_for_job(job_id=job.id)
        moments = await self._moments_for_job(job_id=job.id)
        patterns = await self._patterns_for_job(job_id=job.id)
        content_score = await self._content_score_for_job(job_id=job.id)
        return self._to_response(job, positions, moments, patterns, content_score)

    async def latest_content_score(
        self, *, tenant_id: uuid.UUID, game_id: uuid.UUID
    ) -> ChessContentOpportunityScoreSchema:
        return await load_latest_content_score(self.db, tenant_id=tenant_id, game_id=game_id)

    async def process_job(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessAnalysisJob:
        job = await self._get_job_row(tenant_id=tenant_id, job_id=job_id)
        game = await self.queries.get_game(tenant_id=tenant_id, game_id=job.chess_game_id)
        if game is None:
            job.status = ChessAnalysisJobStatus.FAILED.value
            job.error_message = "Game not found"
            await self.db.flush()
            return job

        job.status = ChessAnalysisJobStatus.RUNNING.value
        job.progress = 0.05
        await self.db.flush()

        try:
            parsed = parse_chess_input(game.normalized_pgn, "pgn")
        except ChessParseError as exc:
            job.status = ChessAnalysisJobStatus.FAILED.value
            job.error_message = str(exc)
            await self.db.flush()
            return job

        engine: ChessEngine | None = None
        started = time.perf_counter()
        try:
            engine = self._open_engine(job)
            plies = analyze_game(
                parsed,
                engine,
                depth=job.depth,
                time_seconds=job.time_limit_seconds,
            )
            persist_analysis_results(
                self.db,
                tenant_id=tenant_id,
                chess_game_id=job.chess_game_id,
                analysis_job_id=job.id,
                plies=plies,
                starting_fen=parsed.starting_fen,
                analysis_settings=dict(job.analysis_settings or {}),
                game=game,
            )
            job.engine_name = engine.name
            job.engine_version = engine.version
            job.ply_count = len(plies)
            job.progress = 1.0
            job.status = ChessAnalysisJobStatus.COMPLETED.value
            job.error_message = None
            record_engine_analysis(
                outcome="success",
                duration_ms=(time.perf_counter() - started) * 1000.0,
                ply_count=len(plies),
                engine_name=engine.name,
            )
        except ChessEngineConfigError as exc:
            logger.warning("chess_analysis_config_error job=%s err=%s", job_id, exc)
            job.status = ChessAnalysisJobStatus.FAILED.value
            job.error_message = str(exc)
            record_engine_analysis(
                outcome="failure",
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error_class="config_error",
            )
        except Exception as exc:  # noqa: BLE001 — persist failure for UI
            logger.exception("chess_analysis_failed job=%s", job_id)
            job.status = ChessAnalysisJobStatus.FAILED.value
            job.error_message = str(exc)[:2000]
            record_engine_analysis(
                outcome="failure",
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error_class=type(exc).__name__,
            )
        finally:
            if engine is not None:
                try:
                    engine.close()
                except Exception:  # noqa: BLE001
                    pass
        await self.db.flush()
        return job

    def _open_engine(self, job: ChessAnalysisJob) -> ChessEngine:
        if self._engine_factory is not None:
            return self._engine_factory()
        return open_stockfish(
            settings.STOCKFISH_PATH,
            hash_mb=job.hash_mb,
            threads=job.threads,
        )

    async def _get_job_row(
        self, *, tenant_id: uuid.UUID, job_id: uuid.UUID
    ) -> ChessAnalysisJob:
        result = await self.db.execute(
            select(ChessAnalysisJob).where(
                ChessAnalysisJob.id == job_id,
                ChessAnalysisJob.tenant_id == tenant_id,
            )
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Analysis job not found")
        return job

    async def _positions_for_job(
        self, *, job_id: uuid.UUID
    ) -> list[ChessPositionAnalysis]:
        result = await self.db.execute(
            select(ChessPositionAnalysis)
            .where(ChessPositionAnalysis.analysis_job_id == job_id)
            .order_by(ChessPositionAnalysis.ply.asc())
        )
        return list(result.scalars().all())

    async def _moments_for_job(self, *, job_id: uuid.UUID) -> list[ChessCriticalMoment]:
        result = await self.db.execute(
            select(ChessCriticalMoment)
            .where(ChessCriticalMoment.analysis_job_id == job_id)
            .order_by(ChessCriticalMoment.ply.asc(), ChessCriticalMoment.classification.asc())
        )
        return list(result.scalars().all())

    async def _patterns_for_job(self, *, job_id: uuid.UUID) -> list[ChessTacticalPattern]:
        result = await self.db.execute(
            select(ChessTacticalPattern)
            .where(ChessTacticalPattern.analysis_job_id == job_id)
            .order_by(ChessTacticalPattern.ply.asc(), ChessTacticalPattern.pattern.asc())
        )
        return list(result.scalars().all())

    async def _content_score_for_job(
        self, *, job_id: uuid.UUID
    ) -> ChessContentOpportunityScore | None:
        result = await self.db.execute(
            select(ChessContentOpportunityScore)
            .where(ChessContentOpportunityScore.analysis_job_id == job_id)
            .order_by(ChessContentOpportunityScore.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_response(
        job: ChessAnalysisJob,
        positions: list[ChessPositionAnalysis],
        moments: list[ChessCriticalMoment] | None = None,
        patterns: list[ChessTacticalPattern] | None = None,
        content_score: ChessContentOpportunityScore | None = None,
    ) -> ChessAnalysisJobResponse:
        score_schema = None
        if content_score is not None:
            score_schema = ChessContentOpportunityScoreSchema.model_validate(
                content_score
            ).model_copy(update={"persisted": True})
        return ChessAnalysisJobResponse(
            id=job.id,
            tenant_id=job.tenant_id,
            chess_game_id=job.chess_game_id,
            status=job.status,
            progress=job.progress,
            error_message=job.error_message,
            depth=job.depth,
            time_limit_seconds=job.time_limit_seconds,
            hash_mb=job.hash_mb,
            threads=job.threads,
            engine_name=job.engine_name,
            engine_version=job.engine_version,
            analysis_settings=job.analysis_settings or {},
            ply_count=job.ply_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
            positions=[ChessPositionAnalysisSchema.model_validate(p) for p in positions],
            critical_moments=[
                ChessCriticalMomentSchema.model_validate(m) for m in (moments or [])
            ],
            tactical_patterns=[
                ChessTacticalPatternSchema.model_validate(p) for p in (patterns or [])
            ],
            content_opportunity=score_schema,
        )
