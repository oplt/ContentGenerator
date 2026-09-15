"""DB pool checkout-wait + query / slow-query instrumentation."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event

from backend.core.config import settings
from backend.core.domain_metrics import domain_metrics
from backend.core.logging import get_logger

logger = get_logger(__name__)

_query_listeners_attached = False


def attach_db_observability(sync_engine: Any) -> None:
    """Idempotent: patch pool checkout timing + cursor query counters."""
    _patch_checkout_wait(sync_engine.pool)
    _attach_query_listeners(sync_engine)


def _patch_checkout_wait(pool: Any) -> None:
    if getattr(pool, "_cg_checkout_wait_patched", False):
        return
    if not hasattr(pool, "_do_get"):
        return

    original = pool._do_get

    def _timed_do_get(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            domain_metrics.record_db_checkout_wait(
                duration_ms=(time.perf_counter() - started) * 1000.0
            )

    pool._do_get = _timed_do_get
    pool._cg_checkout_wait_patched = True


def _attach_query_listeners(sync_engine: Any) -> None:
    global _query_listeners_attached
    if _query_listeners_attached:
        return

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        conn.info["cg_query_start"] = time.perf_counter()
        domain_metrics.record_db_query()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        started = conn.info.pop("cg_query_start", None)
        if started is None:
            return
        duration_ms = (time.perf_counter() - started) * 1000.0
        threshold = float(getattr(settings, "SQL_SLOW_QUERY_MS", 500.0))
        if duration_ms >= threshold:
            domain_metrics.record_db_slow_query()
            logger.warning("slow_query", duration_ms=round(duration_ms, 2))

    _query_listeners_attached = True


def reset_db_observability_state() -> None:
    """Test helper: allow re-attach after engine dispose."""
    global _query_listeners_attached
    _query_listeners_attached = False
