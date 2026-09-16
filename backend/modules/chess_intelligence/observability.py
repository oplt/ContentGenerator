"""Chess intelligence structured logs + domain metrics (Phase 31 / §20).

Answers ops questions via ``cg.operation.*`` / ``cg.chess.import.total`` /
``cg.provider.*`` (HTTP already recorded in ``core.http``):

- How many games/puzzles did we import? → ``cg.chess.import.total``
- How many were duplicates / invalid? → ``result=duplicate|invalid``
- Which provider is failing? → ``cg.provider.request.total`` + provider logs
- How long does Stockfish take? → ``cg.operation.duration_ms`` ``chess.engine.analyze``
- Catalog → video handoffs? → ``chess.video.handoff``

§20 discovery/persistence counters (job ``result`` + logs)::

    discovered fetched parsed normalized
    new_games existing_games new_sources duplicate_sources
    skipped invalid persisted failed
    (+ analysis_* / critical_moments / content_opportunities_created)
    (+ provider: duration_ms, high_water_mark; retries via cg.provider.*)

Never log full PGNs, tokens, or secrets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger

logger = get_logger(__name__)

METRIC_CHESS_IMPORT = "cg.chess.import.total"

OP_ENGINE_ANALYZE = "chess.engine.analyze"
OP_VIDEO_HANDOFF = "chess.video.handoff"
OP_ANALYSIS_ENQUEUE = "chess.analysis.enqueue"
OP_CATALOG_DISCOVERY = "chess.catalog.discovery"

RESULT_INSERTED = "inserted"
RESULT_DUPLICATE = "duplicate"
RESULT_LINKED = "linked"
RESULT_INVALID = "invalid"
RESULT_FILTERED = "filtered"
RESULT_REUSED = "reused"
RESULT_REQUESTED = "requested"

SENSITIVE_LOG_KEYS: frozenset[str] = frozenset(
    {
        "pgn",
        "normalized_pgn",
        "raw_pgn",
        "token",
        "api_token",
        "access_token",
        "authorization",
        "password",
        "secret",
        "lichess_api_token",
        "bearer",
    }
)


def sanitize_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop or redact sensitive keys; never emit full PGN / tokens."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = key.lower()
        if lowered in SENSITIVE_LOG_KEYS or any(
            s in lowered for s in ("token", "secret", "password")
        ):
            out[key] = "[redacted]"
            continue
        if isinstance(value, str) and (
            "[Event " in value or (value.count("\n") > 5 and "1." in value[:200])
        ):
            out[key] = f"[redacted_pgn len={len(value)}]"
            continue
        out[key] = value
    return out


@dataclass
class DiscoveryPersistenceStats:
    """Canonical §20 counters for catalog/import/provider-sync job results."""

    discovered: int = 0
    fetched: int = 0
    parsed: int = 0
    normalized: int = 0
    new_games: int = 0
    existing_games: int = 0
    new_sources: int = 0
    duplicate_sources: int = 0
    skipped: int = 0
    invalid: int = 0
    persisted: int = 0
    failed: int = 0
    duration_ms: float | None = None
    high_water_mark: str | None = None
    analysis_requested: int = 0
    analysis_reused: int = 0
    analysis_started: int = 0
    analysis_completed: int = 0
    analysis_failed: int = 0
    critical_moments: int = 0
    content_opportunities_created: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_result(self) -> dict[str, Any]:
        """Job ``result`` payload: §20 names + backwards-compatible aliases."""
        body: dict[str, Any] = {
            "discovered": self.discovered,
            "fetched": self.fetched,
            "parsed": self.parsed,
            "normalized": self.normalized,
            "new_games": self.new_games,
            "existing_games": self.existing_games,
            "new_sources": self.new_sources,
            "duplicate_sources": self.duplicate_sources,
            "skipped": self.skipped,
            "invalid": self.invalid,
            "persisted": self.persisted,
            "failed": self.failed,
            "scanned": self.discovered,
            "inserted": self.new_games,
            "linked_source": self.new_sources,
            "skipped_duplicate": self.duplicate_sources,
            "skipped_error": self.failed,
            "skipped_filtered": self.skipped,
        }
        if self.duration_ms is not None:
            body["duration_ms"] = round(self.duration_ms, 3)
        if self.high_water_mark is not None:
            body["high_water_mark"] = self.high_water_mark
        if (
            self.analysis_requested
            or self.analysis_reused
            or self.analysis_completed
            or self.critical_moments
            or self.content_opportunities_created
        ):
            body.update(
                {
                    "analysis_requested": self.analysis_requested,
                    "analysis_reused": self.analysis_reused,
                    "analysis_started": self.analysis_started,
                    "analysis_completed": self.analysis_completed,
                    "analysis_failed": self.analysis_failed,
                    "critical_moments": self.critical_moments,
                    "content_opportunities_created": self.content_opportunities_created,
                }
            )
        body.update(self.extra)
        return body


def stats_from_pgn_progress(
    *,
    scanned: int,
    inserted: int,
    linked_source: int,
    skipped_duplicate: int,
    skipped_filtered: int = 0,
    skipped_error: int = 0,
    duration_ms: float | None = None,
    **extra: Any,
) -> DiscoveryPersistenceStats:
    return DiscoveryPersistenceStats(
        discovered=scanned,
        fetched=scanned,
        parsed=max(0, scanned - skipped_error),
        normalized=inserted + linked_source + skipped_duplicate,
        new_games=inserted,
        existing_games=linked_source + skipped_duplicate,
        new_sources=linked_source + inserted,
        duplicate_sources=skipped_duplicate,
        skipped=skipped_filtered,
        invalid=skipped_error,
        persisted=inserted + linked_source,
        failed=skipped_error,
        duration_ms=duration_ms,
        extra={"linked_source": linked_source, **extra},
    )


def stats_from_puzzle_progress(
    *,
    scanned: int,
    inserted: int,
    skipped_duplicate: int,
    filtered: int = 0,
    skipped_error: int = 0,
    duration_ms: float | None = None,
    **extra: Any,
) -> DiscoveryPersistenceStats:
    return DiscoveryPersistenceStats(
        discovered=scanned,
        fetched=scanned,
        parsed=max(0, scanned - skipped_error),
        normalized=inserted + skipped_duplicate,
        skipped=filtered,
        invalid=skipped_error,
        persisted=inserted,
        failed=skipped_error,
        duplicate_sources=skipped_duplicate,
        duration_ms=duration_ms,
        extra={"inserted": inserted, "puzzle": True, **extra},
    )


def stats_from_provider_sync(
    *,
    searched: int,
    in_window: int,
    attempted: int,
    inserted: int,
    linked: int,
    dupes: int,
    errors: int,
    duration_ms: float | None = None,
    high_water_mark: str | None = None,
    **extra: Any,
) -> DiscoveryPersistenceStats:
    succeeded = inserted + linked + dupes
    return DiscoveryPersistenceStats(
        discovered=searched,
        fetched=attempted,
        parsed=succeeded,
        normalized=succeeded,
        new_games=inserted,
        existing_games=linked + dupes,
        new_sources=linked + inserted,
        duplicate_sources=dupes,
        skipped=max(0, searched - in_window),
        persisted=inserted + linked,
        failed=errors,
        duration_ms=duration_ms,
        high_water_mark=high_water_mark,
        extra={
            "searched": searched,
            "in_window": in_window,
            "linked_source": linked,
            **extra,
        },
    )


def record_discovery_persistence(
    *,
    kind: str,
    provider: str,
    stats: DiscoveryPersistenceStats,
    include_import_counters: bool = True,
) -> None:
    """Emit metrics + structured summary for a catalog discovery/persist run.

    Set ``include_import_counters=False`` when the importer already called
    ``record_game_import_progress`` / ``record_puzzle_import_progress``.
    """
    linked = int(stats.extra.get("linked_source", max(0, stats.new_sources - stats.new_games)))
    if include_import_counters:
        if kind == "game":
            record_game_import_progress(
                provider=provider,
                inserted=stats.new_games,
                linked=linked,
                duplicates=stats.duplicate_sources,
                invalid=stats.invalid,
                scanned=stats.discovered,
            )
        elif kind == "puzzle":
            record_puzzle_import_progress(
                provider=provider,
                inserted=int(stats.extra.get("inserted") or stats.persisted),
                duplicates=stats.duplicate_sources,
                invalid=stats.invalid,
                filtered=stats.skipped,
                scanned=stats.discovered,
            )
    domain_metrics.record_operation(
        OP_CATALOG_DISCOVERY,
        outcome="failure" if stats.failed else "success",
        duration_ms=float(stats.duration_ms or 0.0),
    )
    payload = sanitize_log_payload(
        {
            "kind": kind,
            "provider": provider,
            **{k: v for k, v in asdict(stats).items() if k != "extra"},
            **stats.extra,
        }
    )
    logger.info("chess_discovery_persistence", **payload)


def log_provider_request(
    *,
    provider: str,
    action: str,
    outcome: str,
    duration_ms: float,
    status_class: str = "none",
    error_class: str | None = None,
) -> None:
    """Structured provider request/latency/error log."""
    payload: dict[str, Any] = {
        "provider": provider,
        "action": action[:128],
        "outcome": outcome,
        "duration_ms": round(duration_ms, 3),
        "status_class": status_class,
    }
    if error_class:
        payload["error_class"] = error_class
    payload = sanitize_log_payload(payload)
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
        **sanitize_log_payload(
            {
                "provider": provider,
                "scanned": scanned,
                "inserted": inserted,
                "linked": linked,
                "duplicates": duplicates,
                "invalid": invalid,
                "dry_run": dry_run,
                "new_games": inserted,
                "new_sources": linked,
                "duplicate_sources": duplicates,
                "discovered": scanned,
            }
        ),
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
        **sanitize_log_payload(
            {
                "provider": provider,
                "scanned": scanned,
                "inserted": inserted,
                "duplicates": duplicates,
                "invalid": invalid,
                "filtered": filtered,
                "dry_run": dry_run,
                "discovered": scanned,
                "persisted": inserted,
                "skipped": filtered,
            }
        ),
    )


def record_analysis_lifecycle(
    *,
    event: str,
    duration_ms: float = 0.0,
    critical_moments: int | None = None,
    content_opportunities_created: int | None = None,
    error_class: str | None = None,
) -> None:
    """Track analysis_requested / reused / started / completed / failed (§20)."""
    if event in {"analysis_requested", "analysis_reused"}:
        domain_metrics.record_operation(
            OP_ANALYSIS_ENQUEUE,
            outcome="success",
            duration_ms=duration_ms,
            error_class=error_class,
        )
        domain_metrics.record_chess_import(
            kind="analysis",
            provider="stockfish",
            result=RESULT_REUSED if event == "analysis_reused" else RESULT_REQUESTED,
            amount=1,
            operation=OP_ANALYSIS_ENQUEUE,
        )
    payload: dict[str, Any] = {
        "lifecycle_event": event,
        "duration_ms": round(duration_ms, 3),
    }
    if critical_moments is not None:
        payload["critical_moments"] = critical_moments
    if content_opportunities_created is not None:
        payload["content_opportunities_created"] = content_opportunities_created
    if error_class:
        payload["error_class"] = error_class
    logger.info("chess_analysis_lifecycle", **sanitize_log_payload(payload))


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
    payload = sanitize_log_payload(payload)
    if outcome == "success":
        logger.info("chess_engine_analysis", **payload)
        record_analysis_lifecycle(event="analysis_completed", duration_ms=duration_ms)
    else:
        logger.warning("chess_engine_failure", **payload)
        record_analysis_lifecycle(
            event="analysis_failed", duration_ms=duration_ms, error_class=error_class
        )


def record_video_handoff(
    *,
    outcome: str,
    source: str,
    cached: bool = False,
    is_famous: bool | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Catalog/raw game → chess video job."""
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
        **sanitize_log_payload(
            {
                "outcome": outcome,
                "source": source,
                "cached": cached,
                "is_famous": is_famous,
                "duration_ms": round(duration_ms, 3),
            }
        ),
    )
