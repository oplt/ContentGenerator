"""Content-generation stage timing + log context (Phase 15)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from backend.core.domain_metrics import domain_metrics
from backend.core.log_context import bind_log_context


@contextmanager
def generation_stage(stage: str, **log_fields: Any) -> Iterator[None]:
    """Record stage duration/outcome and bind structured log fields."""
    bind_log_context(stage=stage, **log_fields)
    started = perf_counter()
    outcome = "success"
    try:
        yield
    except Exception:
        outcome = "failure"
        raise
    finally:
        domain_metrics.record_generation_stage(
            stage=stage,
            duration_ms=(perf_counter() - started) * 1000.0,
            outcome=outcome,
        )
