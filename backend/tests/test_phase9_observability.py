"""Phase 9: request correlation IDs are safe, propagated, and log-visible.

Full HTTP middleware lifecycle coverage: ``test_correlation_id_propagation.py``.
"""

import logging
import uuid

import structlog

from backend.api.middleware.correlation_id import _request_id
from backend.core.logging import CorrelationIdFilter


def test_request_id_accepts_safe_values_and_replaces_invalid_values() -> None:
    assert _request_id("request-123") == "request-123"
    generated = _request_id("bad request\nwith-newline")
    uuid.UUID(generated)


def test_stdlib_records_receive_correlation_context() -> None:
    structlog.contextvars.bind_contextvars(correlation_id="corr-123")
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)

    assert CorrelationIdFilter().filter(record) is True
    assert record.correlation_id == "corr-123"
    structlog.contextvars.clear_contextvars()
