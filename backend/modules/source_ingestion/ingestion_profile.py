"""Ingestion pipeline stage timing (ops Phase 11) — no prompt/content in metrics."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Iterator

from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger

logger = get_logger("backend.ingestion.profile")

# Stable stage names for metrics / fetch_run metadata.
STAGE_SOURCE_FETCH = "source_fetch"
STAGE_PARSING = "parsing"
STAGE_NORMALIZATION = "normalization"
STAGE_DEDUPLICATION = "deduplication"
STAGE_DATABASE_READS = "database_reads"
STAGE_CLUSTERING = "clustering"
STAGE_DATABASE_WRITES = "database_writes"
STAGE_TOTAL = "total"


@dataclass
class IngestionProfiler:
    """Accumulate stage durations for one ingest_source run."""

    stages_ms: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        started = perf_counter()
        outcome = "success"
        try:
            yield
        except Exception:
            outcome = "failure"
            raise
        finally:
            duration_ms = (perf_counter() - started) * 1000.0
            self.stages_ms[name] = round(duration_ms, 2)
            domain_metrics.record_ingestion_stage(
                stage=name,
                duration_ms=duration_ms,
                outcome=outcome,
            )
            logger.info(
                "ingestion_stage",
                stage=name,
                duration_ms=round(duration_ms, 2),
                outcome=outcome,
            )

    def snapshot(self) -> dict[str, float]:
        return dict(self.stages_ms)


_current: IngestionProfiler | None = None


def get_ingestion_profiler() -> IngestionProfiler | None:
    return _current


@contextmanager
def ingestion_profile_scope() -> Iterator[IngestionProfiler]:
    global _current
    profiler = IngestionProfiler()
    previous = _current
    _current = profiler
    started = perf_counter()
    try:
        yield profiler
    finally:
        profiler.stages_ms[STAGE_TOTAL] = round((perf_counter() - started) * 1000.0, 2)
        domain_metrics.record_ingestion_stage(
            stage=STAGE_TOTAL,
            duration_ms=profiler.stages_ms[STAGE_TOTAL],
            outcome="success",
        )
        _current = previous
