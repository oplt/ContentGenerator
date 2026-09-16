"""Handler-only timing for HTTP list routes (ops Phase 15 profiling)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from backend.core.domain_metrics import domain_metrics
from backend.core.log_context import bind_log_context


@contextmanager
def http_handler_stage(*, operation: str, stage: str) -> Iterator[None]:
    """Measure handler sub-stage duration (excludes auth middleware stack)."""
    bind_log_context(stage=stage)
    started = perf_counter()
    outcome = "success"
    try:
        yield
    except Exception:
        outcome = "failure"
        raise
    finally:
        duration_ms = (perf_counter() - started) * 1000.0
        domain_metrics.record_operation(
            f"{operation}.{stage}",
            outcome=outcome,
            duration_ms=duration_ms,
        )
