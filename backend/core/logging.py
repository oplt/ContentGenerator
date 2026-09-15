from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger  # type: ignore[attr-defined]

from backend.core.config import settings
from backend.core.log_context import drop_sensitive_log_keys

# Create logs directory if it doesn't exist
LOG_DIR = Path("/home/polat/Desktop/Projects/content_generator/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


class CorrelationIdFilter(logging.Filter):
    """Copy async structlog context onto standard-library log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = structlog.contextvars.get_contextvars()
        record.correlation_id = context.get("correlation_id", "n/a")
        return True


def setup_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_signalforge_logging_configured", False):
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Configure file handler with daily rotation
    log_file = LOG_DIR / f"app_{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file)
    
    # Use JSON formatter for structured logging
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(correlation_id)s %(message)s",
        timestamp=True
    )
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    correlation_filter = CorrelationIdFilter()
    root_logger.setLevel(settings.LOG_LEVEL.upper())
    file_handler.addFilter(correlation_filter)
    root_logger.addHandler(file_handler)
    
    # Also keep console output for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(correlation_filter)
    root_logger.addHandler(console_handler)
    root_logger._signalforge_logging_configured = True  # type: ignore[attr-defined]
    logging.getLogger("uvicorn.access").disabled = True
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            drop_sensitive_log_keys,
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


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)

# Cleanup old logs (keep only last 2 days)
def cleanup_old_logs() -> None:
    """Remove log files older than 2 days"""
    now = datetime.now()
    for log_file in LOG_DIR.glob("app_*.log"):
        try:
            # Extract date from filename: app_YYYY-MM-DD.log
            date_str = log_file.stem.split("_")[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            
            # Delete if older than 2 days
            if (now - file_date).days > 2:
                log_file.unlink()
                print(f"Deleted old log file: {log_file}")
        except (IndexError, ValueError):
            # Skip files that don't match the expected pattern
            continue

# Run cleanup on import (for background cleanup)
cleanup_old_logs()
