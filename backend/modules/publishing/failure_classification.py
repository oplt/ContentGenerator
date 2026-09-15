"""Classify publishing provider failures for retry vs manual review."""

from __future__ import annotations

import asyncio
import enum

import httpx
from fastapi import HTTPException


class PublishErrorClass(str, enum.Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AMBIGUOUS = "ambiguous"


_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


def classify_publish_error(exc: BaseException) -> PublishErrorClass:
    """Map provider/transport exceptions to retry policy classes."""
    if isinstance(exc, (httpx.TimeoutException, TimeoutError, asyncio.CancelledError)):
        # Side effect may have completed after the client gave up.
        return PublishErrorClass.AMBIGUOUS

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in _TRANSIENT_STATUS:
            return PublishErrorClass.TRANSIENT
        if 400 <= status < 500:
            return PublishErrorClass.PERMANENT
        return PublishErrorClass.TRANSIENT

    if isinstance(exc, httpx.TransportError):
        return PublishErrorClass.TRANSIENT

    if isinstance(exc, HTTPException):
        if exc.status_code in _TRANSIENT_STATUS or exc.status_code >= 500:
            return PublishErrorClass.TRANSIENT
        if 400 <= exc.status_code < 500:
            return PublishErrorClass.PERMANENT
        return PublishErrorClass.TRANSIENT

    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return PublishErrorClass.AMBIGUOUS
    return PublishErrorClass.TRANSIENT
