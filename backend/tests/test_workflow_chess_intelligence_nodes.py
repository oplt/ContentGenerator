"""Phase 18 — chess intelligence workflow nodes (wrap catalog/analysis services)."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workflows.context import build_node_context
from backend.modules.workflows.engine_inputs import resolve_node_inputs
from backend.modules.workflows.nodes import IMPLEMENTED_SLICE
from backend.modules.workflows.nodes.base import NodeResultStatus
from backend.modules.workflows.nodes.chess import GenerateChessVideoNode
from backend.modules.workflows.nodes.chess_intelligence import (
    AnalyzeChessGameNode,
    GenerateChessNarrativeNode,
    RetrieveChessGameNode,
    RetrieveChessPuzzleNode,
    ScoreChessContentNode,
    SelectCriticalMomentNode,
)
from backend.modules.workflows.registry import build_default_registry, reset_default_registry
from backend.modules.workflows.testing_support import mock_generation_result


@pytest.fixture(autouse=True)
def _registry() -> Iterator[None]:
    reset_default_registry(build_default_registry())
    yield
    reset_default_registry(None)


_CHESS_TYPES = {
    "retrieve_chess_game",
    "retrieve_chess_puzzle",
    "analyze_chess_game",
    "select_critical_moment",
    "score_chess_content",
    "generate_chess_narrative",
    "generate_chess_video",
}


def test_chess_nodes_registered_and_executable() -> None:
    registry = build_default_registry()
    types = {d.type for d in registry.list_definitions()}
    assert _CHESS_TYPES.issubset(types)
    for node_type in _CHESS_TYPES - {"generate_chess_video"}:
        defn = registry.to_definition(registry.get(node_type))
        assert defn.category == "chess"
        assert defn.executable is True
        assert "chess" in defn.required_capabilities


def test_implemented_slice_includes_chess_intelligence() -> None:
    types = {cls.type for cls in IMPLEMENTED_SLICE}
    assert _CHESS_TYPES.issubset(types)


def test_retrieve_chess_game_node() -> None:
    node = RetrieveChessGameNode()
    game_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    game = MagicMock(
        id=game_id,
        normalized_pgn="1. e4 e5",
        white_player="A",
        black_player="B",
        is_famous=True,
        famous_title="Immortal",
        move_count=2,
        opening="King's Pawn",
        eco="C20",
    )

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.service.ChessCatalogService"
        ) as svc_cls:
            svc_cls.return_value.get_game = AsyncMock(return_value=game)
            result = await node.execute(
                ctx,
                node.validate_inputs({"chess_game_id": game_id}),
                node.validate_config({}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["normalized_pgn"] == "1. e4 e5"
        assert result.output["is_famous"] is True

    asyncio.run(_run())


def test_retrieve_chess_puzzle_daily() -> None:
    node = RetrieveChessPuzzleNode()
    puzzle_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    puzzle = MagicMock(
        id=puzzle_id,
        provider="lichess",
        external_id="abc",
        starting_fen="8/8/8/8/8/8/8/8 w - - 0 1",
        solution_moves_uci=["e2e4"],
        solution_moves_san=["e4"],
        rating=1500,
        themes=["mate"],
    )

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.service.ChessCatalogService"
        ) as svc_cls:
            svc_cls.return_value.get_daily_puzzle = AsyncMock(return_value=puzzle)
            result = await node.execute(
                ctx,
                node.validate_inputs({}),
                node.validate_config({"use_daily": True}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["puzzle_id"] == str(puzzle_id)
        assert result.output["solution_moves_san"] == ["e4"]

    asyncio.run(_run())


def test_analyze_chess_game_sync() -> None:
    node = AnalyzeChessGameNode()
    game_id = uuid.uuid4()
    job_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    job = MagicMock(id=job_id, status="completed")
    detail = MagicMock(
        critical_moments=[MagicMock()],
        tactical_patterns=[MagicMock(), MagicMock()],
        content_opportunity=MagicMock(score=72),
    )

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.analysis_service.ChessAnalysisService"
        ) as svc_cls:
            instance = svc_cls.return_value
            instance.enqueue = AsyncMock(return_value=job)
            instance.process_job = AsyncMock(return_value=job)
            instance.get_job = AsyncMock(return_value=detail)
            ctx.db.flush = AsyncMock()
            ctx.db.refresh = AsyncMock()
            result = await node.execute(
                ctx,
                node.validate_inputs({"chess_game_id": game_id}),
                node.validate_config({"sync": True}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["enqueued"] is False
        assert result.output["content_score"] == 72
        assert result.output["tactical_pattern_count"] == 2
        instance.enqueue_celery.assert_not_called()

    asyncio.run(_run())


def test_select_critical_moment_filters() -> None:
    node = SelectCriticalMomentNode()
    game_id = uuid.uuid4()
    job_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    moments = [
        MagicMock(
            id=uuid.uuid4(),
            ply=10,
            classification="blunder",
            confidence=0.9,
            detection_method="eval_delta",
            heuristic_summary="Big drop",
            engine_facts={"delta": -300},
        ),
        MagicMock(
            id=uuid.uuid4(),
            ply=4,
            classification="mistake",
            confidence=0.5,
            detection_method="eval_delta",
            heuristic_summary="Small",
            engine_facts={},
        ),
    ]
    detail = MagicMock(id=job_id, critical_moments=moments)

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.analysis_service.ChessAnalysisService"
        ) as svc_cls:
            svc_cls.return_value.latest_for_game = AsyncMock(return_value=detail)
            result = await node.execute(
                ctx,
                node.validate_inputs({"chess_game_id": game_id}),
                node.validate_config({"min_confidence": 0.7, "limit": 3}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["count"] == 1
        assert result.output["selected"][0]["classification"] == "blunder"

    asyncio.run(_run())


def test_score_chess_content_node() -> None:
    node = ScoreChessContentNode()
    game_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    score = MagicMock(
        score=55,
        components={"video_suitability": 10},
        reasons={"video_suitability": ["moves"]},
        formula_version="content_opportunity_v1",
        persisted=False,
    )

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.analysis_service.ChessAnalysisService"
        ) as svc_cls:
            svc_cls.return_value.latest_content_score = AsyncMock(return_value=score)
            result = await node.execute(
                ctx,
                node.validate_inputs({"chess_game_id": game_id}),
                node.validate_config({}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["score"] == 55
        assert result.output["formula_version"] == "content_opportunity_v1"

    asyncio.run(_run())


def test_generate_chess_narrative_scaffold() -> None:
    node = GenerateChessNarrativeNode()
    game_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    game = MagicMock(
        id=game_id,
        famous_title="Opera Game",
        white_player="Morphy",
        black_player="Duke",
        event="Paris",
        game_date="1858",
        year=1858,
        opening="Italian",
        eco="C50",
        result="1-0",
        move_count=20,
    )

    async def _run() -> None:
        with patch(
            "backend.modules.chess_intelligence.service.ChessCatalogService"
        ) as svc_cls:
            svc_cls.return_value.get_game = AsyncMock(return_value=game)
            result = await node.execute(
                ctx,
                node.validate_inputs(
                    {
                        "chess_game_id": game_id,
                        "content_score": 80,
                        "selected_moments": [
                            {
                                "ply": 12,
                                "classification": "sacrifice",
                                "confidence": 0.95,
                                "heuristic_summary": "Queen sac",
                            }
                        ],
                    }
                ),
                node.validate_config({}),
            )
        assert result.status == NodeResultStatus.SUCCEEDED
        assert "Opera Game" in result.output["narrative"]
        assert "Queen sac" in result.output["narrative"]
        assert result.output["provider"] == "deterministic_scaffold"

    asyncio.run(_run())


def test_generate_chess_video_from_catalog_id() -> None:
    node = GenerateChessVideoNode()
    game_id = uuid.uuid4()
    ctx = build_node_context(tenant_id=uuid.uuid4(), db=MagicMock(spec=AsyncSession))
    job = MagicMock(
        id=uuid.uuid4(),
        status="queued",
        video_public_url=None,
        thumbnail_public_url=None,
        render_fingerprint=None,
        move_count=8,
    )

    async def _run() -> None:
        with patch(
            "backend.modules.workflows.nodes.chess.ChessVideoService"
        ) as svc_cls:
            instance = svc_cls.return_value
            instance.create = AsyncMock(return_value=job)
            instance.enqueue_job = MagicMock()
            result = await node.execute(
                ctx,
                node.validate_inputs({"chess_game_id": game_id, "title": "From catalog"}),
                node.validate_config({"sync": False}),
            )
            payload = instance.create.await_args.kwargs["payload"]
            assert payload.chess_game_id == game_id
            assert payload.source_text is None
        assert result.status == NodeResultStatus.SUCCEEDED
        assert result.output["enqueued"] is True

    asyncio.run(_run())


def test_legacy_inputs_map_catalog_game_to_video() -> None:
    game_id = uuid.uuid4()
    mapped = resolve_node_inputs(
        node_type="generate_chess_video",
        trigger_payload={},
        initial_inputs={
            "chess_game_id": game_id,
            "normalized_pgn": "1. e4 e5",
            "famous_title": "Immortal",
        },
        upstream_outputs=[],
    )
    assert mapped["chess_game_id"] == game_id
    assert mapped["source_text"] == "1. e4 e5"
    assert mapped["title"] == "Immortal"


def test_mock_chess_narrative() -> None:
    result = mock_generation_result(
        "generate_chess_narrative",
        {"chess_game_id": "abc", "selected_moments": [{}, {}]},
    )
    assert result.status == NodeResultStatus.SUCCEEDED
    assert result.output["moment_count"] == 2
    assert result.output["provider"] == "mock"
