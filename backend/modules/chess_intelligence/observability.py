"""Chess intelligence structured logs + domain metrics (Phase 31).

Answers ops questions via ``cg.operation.*`` / ``cg.chess.import.total`` /
``cg.provider.*`` (HTTP already recorded in ``core.http``):

- How many games/puzzles did we import? → ``cg.chess.import.total``
- How many were duplicates / invalid? → ``result=duplicate|invalid``
- Which provider is failing? → ``cg.provider.request.total`` + provider logs
- How long does Stockfish take? → ``cg.operation.duration_ms`` ``chess.engine.analyze``
- Catalog → video handoffs? → ``chess.video.handoff``
"""

from __future__ import annotations

from typing import Any

from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger

logger = get_logger(__name__)

# Metric series (also registered in domain_metrics_store / OTel bind).
METRIC_CHESS_IMPORT = "cg.chess.import.total"

OP_ENGINE_ANALYZE = "chess.engine.analyze"
OP_VIDEO_HANDOFF = "chess.video.handoff"

# Import result labels (low cardinality).
RESULT_INSERTED = "inserted"
RESULT_DUPLICATE = "duplicate"
RESULT_LINKED = "linked"
RESULT_INVALID = "invalid"
RESULT_FILTERED = "filtered"


def log_provider_request(
    *,
    provider: str,
    action: str,
    outcome: str,
    duration_ms: float,
    status_class: str = "none",
    error_class: str | None = None,
) -> None:
    """Structured provider request/latency/error log.

    Duration/outcome metrics for HTTP already emit via ``core.http`` →
    ``cg.provider.request.*``. This log adds chess-specific action context.
    """
    payload: dict[str, Any] = {
        "provider": provider,
        "action": action[:128],
        "outcome": outcome,
        "duration_ms": round(duration_ms, 3),
        "status_class": status_class,
    }
    if error_class:
        payload["error_class"] = error_class
    if outcome in {"failure", "transport_error", "client_error"}:
        logger.warning("chess_provider_request", **payload)
    else:
        logger.info("chess_provider_request", **payload)


def record_game_import_progress(
    *,
    provider: str,
    inserted: int = 0,
    linked: int = 0,
    duplicates: int = 0,
    invalid: int = 0,
    scanned: int = 0,
    dry_run: bool = False,
) -> None:
    """Emit import counters + summary log for PGN / catalog game ingest."""
    domain_metrics.record_chess_import(
        kind="game", provider=provider, result=RESULT_INSERTED, amount=inserted
    )
    domain_metrics.record_chess_import(
        kind="game", provider=provider, result=RESULT_LINKED, amount=linked
    )
    domain_metrics.record_chess_import(
        kind="game", provider=provider, result=RESULT_DUPLICATE, amount=duplicates
    )
    domain_metrics.record_chess_import(
        kind="game", provider=provider, result=RESULT_INVALID, amount=invalid
    )
    logger.info(
        "chess_game_import_done",
        provider=provider,
        scanned=scanned,
        inserted=inserted,
        linked=linked,
        duplicates=duplicates,
        invalid=invalid,
        dry_run=dry_run,
    )


def record_puzzle_import_progress(
    *,
    provider: str,
    inserted: int = 0,
    duplicates: int = 0,
    invalid: int = 0,
    filtered: int = 0,
    scanned: int = 0,
    dry_run: bool = False,
) -> None:
    domain_metrics.record_chess_import(
        kind="puzzle", provider=provider, result=RESULT_INSERTED, amount=inserted
    )
    domain_metrics.record_chess_import(
        kind="puzzle", provider=provider, result=RESULT_DUPLICATE, amount=duplicates
    )
    domain_metrics.record_chess_import(
        kind="puzzle", provider=provider, result=RESULT_INVALID, amount=invalid
    )
    domain_metrics.record_chess_import(
        kind="puzzle", provider=provider, result=RESULT_FILTERED, amount=filtered
    )
    logger.info(
        "chess_puzzle_import_done",
        provider=provider,
        scanned=scanned,
        inserted=inserted,
        duplicates=duplicates,
        invalid=invalid,
        filtered=filtered,
        dry_run=dry_run,
    )


def record_engine_analysis(
    *,
    outcome: str,
    duration_ms: float,
    error_class: str | None = None,
    ply_count: int | None = None,
    engine_name: str | None = None,
) -> None:
    domain_metrics.record_operation(
        OP_ENGINE_ANALYZE,
        outcome=outcome,
        duration_ms=duration_ms,
        error_class=error_class,
    )
    payload: dict[str, Any] = {
        "outcome": outcome,
        "duration_ms": round(duration_ms, 3),
    }
    if ply_count is not None:
        payload["ply_count"] = ply_count
    if engine_name:
        payload["engine_name"] = engine_name[:64]
    if error_class:
        payload["error_class"] = error_class
    if outcome == "success":
        logger.info("chess_engine_analysis", **payload)
    else:
        logger.warning("chess_engine_failure", **payload)


def record_video_handoff(
    *,
    outcome: str,
    source: str,
    cached: bool = False,
    is_famous: bool | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Catalog/raw game → chess video job.

    ``source``: catalog | paste | famous (low cardinality).
    Successful publishes from chess videos still use ``cg.publish.*``;
    join via logs / ``chess_game_id`` on the video job, not metric labels.
    """
    domain_metrics.record_operation(
        OP_VIDEO_HANDOFF,
        outcome=outcome,
        duration_ms=duration_ms,
    )
    if outcome == "success":
        domain_metrics.record_chess_import(
            kind="video",
            provider=source,
            result="cached" if cached else "queued",
            amount=1,
            operation=OP_VIDEO_HANDOFF,
        )
    logger.info(
        "chess_video_handoff",
        outcome=outcome,
        source=source,
        cached=cached,
        is_famous=is_famous,
        duration_ms=round(duration_ms, 3),
    )
