"""Persist Stockfish ply rows + critical moments + tactics + content score."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.chess_intelligence.content_opportunity import score_from_entities
from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis
from backend.modules.chess_intelligence.engine.critical_moments import detect_critical_moments
from backend.modules.chess_intelligence.engine.tactical_patterns import detect_tactical_patterns
from backend.modules.chess_intelligence.models import (
    ChessContentOpportunityScore,
    ChessCriticalMoment,
    ChessGame,
    ChessPositionAnalysis,
    ChessTacticalPattern,
)


def persist_analysis_results(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    chess_game_id: uuid.UUID,
    analysis_job_id: uuid.UUID,
    plies: list[PlyAnalysis],
    starting_fen: str,
    analysis_settings: dict[str, Any],
    game: ChessGame | None = None,
) -> ChessContentOpportunityScore | None:
    settings = dict(analysis_settings or {})
    for ply in plies:
        db.add(
            ChessPositionAnalysis(
                tenant_id=tenant_id,
                chess_game_id=chess_game_id,
                analysis_job_id=analysis_job_id,
                ply=ply.ply,
                fen=ply.fen,
                evaluation_cp=ply.evaluation_cp,
                mate_in=ply.mate_in,
                evaluation_before_cp=ply.evaluation_before_cp,
                mate_before=ply.mate_before,
                evaluation_after_cp=ply.evaluation_after_cp,
                mate_after=ply.mate_after,
                evaluation_delta=ply.evaluation_delta,
                best_move_uci=ply.best_move_uci,
                best_move_san=ply.best_move_san,
                played_move_uci=ply.played_move_uci,
                played_move_san=ply.played_move_san,
                depth=ply.depth,
                nodes=ply.nodes,
                engine_name=ply.engine_name,
                engine_version=ply.engine_version,
                analysis_settings=settings,
            )
        )
    moments = detect_critical_moments(plies, starting_fen=starting_fen)
    for moment in moments:
        db.add(
            ChessCriticalMoment(
                tenant_id=tenant_id,
                chess_game_id=chess_game_id,
                analysis_job_id=analysis_job_id,
                ply=moment.ply,
                classification=moment.classification,
                confidence=moment.confidence,
                detection_method=moment.detection_method,
                engine_facts=moment.engine_facts,
                heuristic_summary=moment.heuristic_summary,
                editorial_description=None,
            )
        )
    patterns = detect_tactical_patterns(plies, starting_fen=starting_fen)
    for pattern in patterns:
        db.add(
            ChessTacticalPattern(
                tenant_id=tenant_id,
                chess_game_id=chess_game_id,
                analysis_job_id=analysis_job_id,
                ply=pattern.ply,
                pattern=pattern.pattern,
                confidence=pattern.confidence,
                detection_method=pattern.detection_method,
                facts=pattern.facts,
                summary=pattern.summary,
            )
        )

    if game is None:
        return None
    result = score_from_entities(
        game=game,
        moment_classifications=[m.classification for m in moments],
        tactical_patterns=[p.pattern for p in patterns],
    )
    row = ChessContentOpportunityScore(
        tenant_id=tenant_id,
        chess_game_id=chess_game_id,
        analysis_job_id=analysis_job_id,
        score=result.score,
        components=dict(result.components),
        reasons=dict(result.reasons),
        formula_version=result.formula_version,
    )
    db.add(row)
    return row
