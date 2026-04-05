from __future__ import annotations

import logging
import sys

import structlog

from backend.core.config import settings


def setup_logging() -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
