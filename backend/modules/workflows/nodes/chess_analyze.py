"""Analyze / select / score chess workflow nodes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.modules.workflows.nodes.base import (
    EmptyModel,
    NodePort,
    NodeResult,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.nodes.chess_common import ok
from backend.modules.workflows.nodes.media_common import fail, require_db


class AnalyzeChessGameConfig(BaseModel):
    depth: int | None = Field(default=None, ge=1, le=40)
    time_limit_seconds: float | None = Field(default=None, gt=0, le=60)
    # sync=True runs Stockfish inline (tests/small); default enqueue Celery.
    sync: bool = False


class AnalyzeChessGameInput(BaseModel):
    chess_game_id: UUID


class AnalyzeChessGameOutput(BaseModel):
    analysis_job_id: str
    chess_game_id: str
    status: str
    enqueued: bool = False
    critical_moment_count: int = 0
    tactical_pattern_count: int = 0
    content_score: int | None = None


class AnalyzeChessGameNode(
    WorkflowNode[AnalyzeChessGameConfig, AnalyzeChessGameInput, AnalyzeChessGameOutput]
):
    type = "analyze_chess_game"
    version = 1
    category = "chess"
    display_name = "Analyze Chess Game"
    description = "Enqueue/run Stockfish analysis + critical moments + content score."
    ConfigSchema = AnalyzeChessGameConfig
    InputSchema = AnalyzeChessGameInput
    OutputSchema = AnalyzeChessGameOutput
    required_capabilities = ["chess"]
    input_ports = [NodePort(name="chess_game_id", data_type="uuid")]
    output_ports = [
        NodePort(name="analysis_job_id", data_type="string"),
        NodePort(name="status", data_type="string"),
        NodePort(name="content_score", data_type="number", required=False),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        typed_in = AnalyzeChessGameInput.model_validate(inputs.model_dump())
        typed_cfg = AnalyzeChessGameConfig.model_validate(config.model_dump())
        from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService
        from backend.modules.chess_intelligence.schemas import ChessAnalysisRequest

        assert context.db is not None
        svc = ChessAnalysisService(context.db)
        try:
            job = await svc.enqueue(
                tenant_id=context.tenant_id,
                user_id=None,
                game_id=typed_in.chess_game_id,
                payload=ChessAnalysisRequest(
                    depth=typed_cfg.depth,
                    time_limit_seconds=typed_cfg.time_limit_seconds,
                ),
            )
            await context.db.flush()
            await context.db.refresh(job)
            enqueued = False
            if typed_cfg.sync:
                job = await svc.process_job(tenant_id=context.tenant_id, job_id=job.id)
                await context.db.flush()
            else:
                svc.enqueue_celery(tenant_id=context.tenant_id, job_id=job.id)
                enqueued = True
            detail = await svc.get_job(tenant_id=context.tenant_id, job_id=job.id)
        except HTTPException as exc:
            return fail("analyze_chess_game_failed", str(exc.detail))
        score = (
            detail.content_opportunity.score if detail.content_opportunity is not None else None
        )
        return ok(
            AnalyzeChessGameOutput(
                analysis_job_id=str(job.id),
                chess_game_id=str(typed_in.chess_game_id),
                status=job.status,
                enqueued=enqueued,
                critical_moment_count=len(detail.critical_moments),
                tactical_pattern_count=len(detail.tactical_patterns),
                content_score=score,
            )
        )


class SelectCriticalMomentConfig(BaseModel):
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    classifications: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)


class SelectCriticalMomentInput(BaseModel):
    chess_game_id: UUID
    analysis_job_id: UUID | None = None


class SelectCriticalMomentOutput(BaseModel):
    chess_game_id: str
    analysis_job_id: str | None = None
    selected: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class SelectCriticalMomentNode(
    WorkflowNode[SelectCriticalMomentConfig, SelectCriticalMomentInput, SelectCriticalMomentOutput]
):
    type = "select_critical_moment"
    version = 1
    category = "chess"
    display_name = "Select Critical Moment"
    description = "Pick top heuristic critical moments from the latest (or given) analysis."
    ConfigSchema = SelectCriticalMomentConfig
    InputSchema = SelectCriticalMomentInput
    OutputSchema = SelectCriticalMomentOutput
    required_capabilities = ["chess"]
    input_ports = [
        NodePort(name="chess_game_id", data_type="uuid"),
        NodePort(name="analysis_job_id", data_type="uuid", required=False),
    ]
    output_ports = [
        NodePort(name="selected", data_type="array"),
        NodePort(name="count", data_type="number"),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        typed_in = SelectCriticalMomentInput.model_validate(inputs.model_dump())
        typed_cfg = SelectCriticalMomentConfig.model_validate(config.model_dump())
        from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService

        assert context.db is not None
        svc = ChessAnalysisService(context.db)
        try:
            if typed_in.analysis_job_id is not None:
                detail = await svc.get_job(
                    tenant_id=context.tenant_id, job_id=typed_in.analysis_job_id
                )
            else:
                detail = await svc.latest_for_game(
                    tenant_id=context.tenant_id, game_id=typed_in.chess_game_id
                )
                if detail is None:
                    return fail("select_critical_moment_failed", "No analysis for this game")
        except HTTPException as exc:
            return fail("select_critical_moment_failed", str(exc.detail))

        allowed = {c.strip().lower() for c in typed_cfg.classifications if c.strip()}
        rows = []
        for moment in detail.critical_moments:
            if moment.confidence < typed_cfg.min_confidence:
                continue
            if allowed and moment.classification.lower() not in allowed:
                continue
            rows.append(
                {
                    "id": str(moment.id),
                    "ply": moment.ply,
                    "classification": moment.classification,
                    "confidence": moment.confidence,
                    "detection_method": moment.detection_method,
                    "heuristic_summary": moment.heuristic_summary,
                    "engine_facts": moment.engine_facts,
                }
            )
        rows.sort(key=lambda r: (-float(r["confidence"]), int(r["ply"])))
        selected = rows[: typed_cfg.limit]
        return ok(
            SelectCriticalMomentOutput(
                chess_game_id=str(typed_in.chess_game_id),
                analysis_job_id=str(detail.id),
                selected=selected,
                count=len(selected),
            )
        )


class ScoreChessContentInput(BaseModel):
    chess_game_id: UUID


class ScoreChessContentOutput(BaseModel):
    chess_game_id: str
    score: int
    components: dict[str, int] = Field(default_factory=dict)
    reasons: dict[str, list[str]] = Field(default_factory=dict)
    formula_version: str
    persisted: bool = False


class ScoreChessContentNode(
    WorkflowNode[EmptyModel, ScoreChessContentInput, ScoreChessContentOutput]
):
    type = "score_chess_content"
    version = 1
    category = "chess"
    display_name = "Score Chess Content Opportunity"
    description = "Transparent content-opportunity score for a catalog game."
    ConfigSchema = EmptyModel
    InputSchema = ScoreChessContentInput
    OutputSchema = ScoreChessContentOutput
    required_capabilities = ["chess"]
    input_ports = [NodePort(name="chess_game_id", data_type="uuid")]
    output_ports = [
        NodePort(name="score", data_type="number"),
        NodePort(name="components", data_type="object", required=False),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        _ = config
        missing = require_db(context)
        if missing is not None:
            return missing
        typed = ScoreChessContentInput.model_validate(inputs.model_dump())
        from backend.modules.chess_intelligence.analysis_service import ChessAnalysisService

        assert context.db is not None
        try:
            score = await ChessAnalysisService(context.db).latest_content_score(
                tenant_id=context.tenant_id, game_id=typed.chess_game_id
            )
        except HTTPException as exc:
            return fail("score_chess_content_failed", str(exc.detail))
        return ok(
            ScoreChessContentOutput(
                chess_game_id=str(typed.chess_game_id),
                score=score.score,
                components=dict(score.components),
                reasons={k: list(v) for k, v in score.reasons.items()},
                formula_version=score.formula_version,
                persisted=bool(score.persisted),
            )
        )
