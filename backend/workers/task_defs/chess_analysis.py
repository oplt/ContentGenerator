from __future__ import annotations

from uuid import UUID

from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
from backend.workers.runtime import run_async_task
from backend.workers.task_defs._common import enqueue_payload, task as _task


@_task("backend.workers.tasks.analyze_chess_game_task")
def analyze_chess_game_task(*, tenant_id: str, job_id: str) -> dict[str, str]:
    async def operation(db):
        job = await ChessAnalysisService(db).process_job(
            tenant_id=UUID(tenant_id),
            job_id=UUID(job_id),
        )
        return {"job_id": str(job.id), "status": job.status}

    return run_async_task(
        task_name="analyze_chess_game",
        queue_name="video",
        tenant_id=UUID(tenant_id),
        entity_type="chess_analysis_job",
        entity_id=job_id,
        celery_task_id=analyze_chess_game_task.request.id,
        correlation_id=analyze_chess_game_task.request.id,
        payload=enqueue_payload(job_id=job_id, kind="chess_analysis"),
        operation=operation,
    )
