"""Chess video node — wraps ChessVideoService (no PGN/render duplication)."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.modules.chess_video.models import ChessVideoJobStatus
from backend.modules.chess_video.schemas import ChessVideoCreateRequest
from backend.modules.chess_video.service import ChessVideoService
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)
from backend.modules.workflows.nodes.media_common import fail, require_db


class GenerateChessVideoConfig(BaseModel):
    input_format: str = Field(default="auto", pattern="^(pgn|san|uci|auto)$")
    orientation: str = Field(default="white", pattern="^(white|black)$")
    render_preset: str = Field(
        default="economy_vertical",
        pattern="^(economy_vertical|social_vertical|square|horizontal)$",
    )
    board_theme: str = Field(
        default="classic_wood",
        pattern="^(classic_wood|tournament_green|midnight_blue|slate|high_contrast)$",
    )
    seconds_per_move: float = Field(default=1.0, ge=0.2, le=10.0)
    include_coordinates: bool = True
    include_move_text: bool = True
    # sync=True runs process_job inline (tests/small jobs); default enqueue Celery.
    sync: bool = False


class GenerateChessVideoInput(BaseModel):
    """Provide ``source_text`` and/or ``chess_game_id`` (catalog bridge)."""

    source_text: str | None = None
    chess_game_id: UUID | None = None
    title: str | None = None
    subtitle: str | None = None

    @model_validator(mode="after")
    def _require_source(self) -> GenerateChessVideoInput:
        text = (self.source_text or "").strip()
        self.source_text = text or None
        if self.source_text is None and self.chess_game_id is None:
            raise ValueError("Provide source_text or chess_game_id")
        return self


class GenerateChessVideoOutput(BaseModel):
    chess_video_job_id: str
    status: str
    video_public_url: str | None = None
    thumbnail_public_url: str | None = None
    render_fingerprint: str | None = None
    move_count: int = 0
    enqueued: bool = False


class GenerateChessVideoNode(
    WorkflowNode[GenerateChessVideoConfig, GenerateChessVideoInput, GenerateChessVideoOutput]
):
    type = "generate_chess_video"
    version = 1
    category = "media"
    display_name = "Generate Chess Video"
    description = "Wrap chess_video service — no PGN/render duplication."
    ConfigSchema = GenerateChessVideoConfig
    InputSchema = GenerateChessVideoInput
    OutputSchema = GenerateChessVideoOutput
    required_capabilities = ["video", "chess"]
    input_ports = [
        NodePort(name="source_text", data_type="string", required=False),
        NodePort(name="chess_game_id", data_type="uuid", required=False),
        NodePort(name="title", data_type="string", required=False),
        NodePort(name="subtitle", data_type="string", required=False),
    ]
    output_ports = [
        NodePort(name="chess_video_job_id", data_type="string"),
        NodePort(name="status", data_type="string"),
        NodePort(name="video_public_url", data_type="string", required=False),
        NodePort(name="thumbnail_public_url", data_type="string", required=False),
        NodePort(name="render_fingerprint", data_type="string", required=False),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        typed_in = GenerateChessVideoInput.model_validate(inputs.model_dump())
        typed_cfg = GenerateChessVideoConfig.model_validate(config.model_dump())
        assert context.db is not None
        payload = ChessVideoCreateRequest(
            source_text=typed_in.source_text,
            chess_game_id=typed_in.chess_game_id,
            input_format=typed_cfg.input_format,
            orientation=typed_cfg.orientation,
            render_preset=typed_cfg.render_preset,
            board_theme=typed_cfg.board_theme,
            seconds_per_move=typed_cfg.seconds_per_move,
            include_coordinates=typed_cfg.include_coordinates,
            include_move_text=typed_cfg.include_move_text,
            title=typed_in.title,
            subtitle=typed_in.subtitle,
        )
        svc = ChessVideoService(context.db)
        try:
            job = await svc.create(
                tenant_id=context.tenant_id,
                user_id=None,
                payload=payload,
            )
        except HTTPException as exc:
            return fail("chess_video_create_failed", str(exc.detail))

        enqueued = False
        if job.status == ChessVideoJobStatus.QUEUED.value:
            if typed_cfg.sync:
                job = await svc.process_job(tenant_id=context.tenant_id, job_id=job.id)
            else:
                svc.enqueue_job(tenant_id=context.tenant_id, job_id=job.id)
                enqueued = True

        out = GenerateChessVideoOutput(
            chess_video_job_id=str(job.id),
            status=job.status,
            video_public_url=job.video_public_url,
            thumbnail_public_url=job.thumbnail_public_url,
            render_fingerprint=job.render_fingerprint,
            move_count=int(job.move_count or 0),
            enqueued=enqueued,
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=out.model_dump())
