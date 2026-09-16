"""Chess engine analysis package (Stockfish binary via python-chess)."""

from backend.modules.chess_intelligence.engine.analyzer import PlyAnalysis, analyze_game
from backend.modules.chess_intelligence.engine.base import (
    ChessEngine,
    EngineLimit,
    EngineScore,
    PositionEngineResult,
)
from backend.modules.chess_intelligence.engine.critical_moments import (
    CriticalMomentCandidate,
    detect_critical_moments,
)
from backend.modules.chess_intelligence.engine.scores import format_score, score_delta
from backend.modules.chess_intelligence.engine.stockfish import (
    ChessEngineConfigError,
    open_stockfish,
)
from backend.modules.chess_intelligence.engine.tactical_patterns import (
    TacticalPatternCandidate,
    detect_tactical_patterns,
)

__all__ = [
    "ChessEngine",
    "ChessEngineConfigError",
    "CriticalMomentCandidate",
    "EngineLimit",
    "EngineScore",
    "PlyAnalysis",
    "PositionEngineResult",
    "TacticalPatternCandidate",
    "analyze_game",
    "detect_critical_moments",
    "detect_tactical_patterns",
    "format_score",
    "open_stockfish",
    "score_delta",
]
