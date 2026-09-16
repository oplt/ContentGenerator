"""Retrieve chess game / puzzle workflow nodes."""

from __future__ import annotations

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


class RetrieveChessGameInput(BaseModel):
    chess_game_id: UUID


class RetrieveChessGameOutput(BaseModel):
    chess_game_id: str
    normalized_pgn: str
    white_player: str | None = None
    black_player: str | None = None
    is_famous: bool = False
    famous_title: str | None = None
    move_count: int = 0
    opening: str | None = None
    eco: str | None = None


class RetrieveChessGameNode(
    WorkflowNode[EmptyModel, RetrieveChessGameInput, RetrieveChessGameOutput]
):
    type = "retrieve_chess_game"
    version = 1
    category = "chess"
    display_name = "Retrieve Chess Game"
    description = "Load a catalog ChessGame (PGN + metadata) for downstream nodes."
    ConfigSchema = EmptyModel
    InputSchema = RetrieveChessGameInput
    OutputSchema = RetrieveChessGameOutput
    required_capabilities = ["chess"]
    input_ports = [NodePort(name="chess_game_id", data_type="uuid")]
    output_ports = [
        NodePort(name="chess_game_id", data_type="string"),
        NodePort(name="normalized_pgn", data_type="string"),
        NodePort(name="white_player", data_type="string", required=False),
        NodePort(name="black_player", data_type="string", required=False),
        NodePort(name="is_famous", data_type="boolean", required=False),
        NodePort(name="famous_title", data_type="string", required=False),
        NodePort(name="move_count", data_type="number", required=False),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        _ = config
        missing = require_db(context)
        if missing is not None:
            return missing
        typed = RetrieveChessGameInput.model_validate(inputs.model_dump())
        from backend.modules.chess_intelligence.service import ChessCatalogService

        assert context.db is not None
        try:
            game = await ChessCatalogService(context.db).get_game(
                tenant_id=context.tenant_id, game_id=typed.chess_game_id
            )
        except HTTPException as exc:
            return fail("retrieve_chess_game_failed", str(exc.detail))
        return ok(
            RetrieveChessGameOutput(
                chess_game_id=str(game.id),
                normalized_pgn=game.normalized_pgn,
                white_player=game.white_player,
                black_player=game.black_player,
                is_famous=game.is_famous,
                famous_title=game.famous_title,
                move_count=game.move_count,
                opening=game.opening,
                eco=game.eco,
            )
        )


class RetrieveChessPuzzleConfig(BaseModel):
    use_daily: bool = False


class RetrieveChessPuzzleInput(BaseModel):
    puzzle_id: UUID | None = None


class RetrieveChessPuzzleOutput(BaseModel):
    puzzle_id: str
    provider: str
    external_id: str
    starting_fen: str
    solution_moves_uci: list[str] = Field(default_factory=list)
    solution_moves_san: list[str] = Field(default_factory=list)
    rating: int | None = None
    themes: list[str] = Field(default_factory=list)


class RetrieveChessPuzzleNode(
    WorkflowNode[RetrieveChessPuzzleConfig, RetrieveChessPuzzleInput, RetrieveChessPuzzleOutput]
):
    type = "retrieve_chess_puzzle"
    version = 1
    category = "chess"
    display_name = "Retrieve Chess Puzzle"
    description = "Load a catalog puzzle by id, or fetch/store today's daily puzzle."
    ConfigSchema = RetrieveChessPuzzleConfig
    InputSchema = RetrieveChessPuzzleInput
    OutputSchema = RetrieveChessPuzzleOutput
    required_capabilities = ["chess"]
    input_ports = [NodePort(name="puzzle_id", data_type="uuid", required=False)]
    output_ports = [
        NodePort(name="puzzle_id", data_type="string"),
        NodePort(name="starting_fen", data_type="string"),
        NodePort(name="solution_moves_san", data_type="array", required=False),
    ]

    async def execute(
        self, context: WorkflowNodeContext, inputs: BaseModel, config: BaseModel
    ) -> NodeResult:
        missing = require_db(context)
        if missing is not None:
            return missing
        typed_in = RetrieveChessPuzzleInput.model_validate(inputs.model_dump())
        typed_cfg = RetrieveChessPuzzleConfig.model_validate(config.model_dump())
        from backend.modules.chess_intelligence.service import ChessCatalogService

        assert context.db is not None
        svc = ChessCatalogService(context.db)
        try:
            if typed_cfg.use_daily or typed_in.puzzle_id is None:
                puzzle = await svc.get_daily_puzzle(tenant_id=context.tenant_id)
            else:
                puzzle = await svc.get_puzzle(
                    tenant_id=context.tenant_id, puzzle_id=typed_in.puzzle_id
                )
        except HTTPException as exc:
            return fail("retrieve_chess_puzzle_failed", str(exc.detail))
        return ok(
            RetrieveChessPuzzleOutput(
                puzzle_id=str(puzzle.id),
                provider=puzzle.provider,
                external_id=puzzle.external_id,
                starting_fen=puzzle.starting_fen,
                solution_moves_uci=list(puzzle.solution_moves_uci or []),
                solution_moves_san=list(puzzle.solution_moves_san or []),
                rating=puzzle.rating,
                themes=list(puzzle.themes or []),
            )
        )
