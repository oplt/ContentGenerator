"""Deterministic chess narrative scaffold workflow node."""

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


class GenerateChessNarrativeInput(BaseModel):
    chess_game_id: UUID
    selected_moments: list[dict[str, Any]] = Field(default_factory=list)
    content_score: int | None = None


class GenerateChessNarrativeOutput(BaseModel):
    chess_game_id: str
    narrative: str
    moment_count: int = 0
    provider: str = "deterministic_scaffold"


class GenerateChessNarrativeNode(
    WorkflowNode[EmptyModel, GenerateChessNarrativeInput, GenerateChessNarrativeOutput]
):
    type = "generate_chess_narrative"
    version = 1
    category = "chess"
    display_name = "Generate Chess Narrative"
    description = (
        "Deterministic editorial scaffold from game + selected moments (not LLM copy)."
    )
    ConfigSchema = EmptyModel
    InputSchema = GenerateChessNarrativeInput
    OutputSchema = GenerateChessNarrativeOutput
    required_capabilities = ["chess"]
    input_ports = [
        NodePort(name="chess_game_id", data_type="uuid"),
        NodePort(name="selected_moments", data_type="array", required=False),
        NodePort(name="content_score", data_type="number", required=False),
    ]
    output_ports = [
        NodePort(name="narrative", data_type="string"),
        NodePort(name="moment_count", data_type="number", required=False),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        _ = config
        missing = require_db(context)
        if missing is not None:
            return missing
        typed = GenerateChessNarrativeInput.model_validate(inputs.model_dump())
        from backend.modules.chess_intelligence.service import ChessCatalogService

        assert context.db is not None
        try:
            game = await ChessCatalogService(context.db).get_game(
                tenant_id=context.tenant_id, game_id=typed.chess_game_id
            )
        except HTTPException as exc:
            return fail("generate_chess_narrative_failed", str(exc.detail))

        title = game.famous_title or (
            f"{game.white_player or 'White'} vs {game.black_player or 'Black'}"
        )
        lines = [
            f"# {title}",
            "",
            f"Event: {game.event or '—'} · Date: {game.game_date or game.year or '—'}",
            f"Opening: {game.opening or '—'} ({game.eco or '—'}) · Result: {game.result or '—'}",
            f"Moves: {game.move_count}",
        ]
        if typed.content_score is not None:
            lines.append(f"Content opportunity score: {typed.content_score}/100")
        lines.append("")
        lines.append("## Critical moments (engine + heuristics)")
        if typed.selected_moments:
            for moment in typed.selected_moments:
                lines.append(
                    f"- Ply {moment.get('ply')}: {moment.get('classification')} "
                    f"(conf {moment.get('confidence')}) — {moment.get('heuristic_summary')}"
                )
        else:
            lines.append("- (none selected — run select_critical_moment upstream)")
        lines.extend(
            [
                "",
                "## Editorial note",
                "This scaffold is deterministic. Human/LLM editorial copy is a later step.",
            ]
        )
        narrative = "\n".join(lines)
        return ok(
            GenerateChessNarrativeOutput(
                chess_game_id=str(game.id),
                narrative=narrative,
                moment_count=len(typed.selected_moments),
            )
        )
