"""Shared Redis value codec (Phase 5.1).

All application cache get/set paths encode and decode through this module so
JSON, strings, and numbers share one wire format. Corrupt/legacy payloads decode
as a miss (``CodecMiss``) instead of raising into multi-get callers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CodecMiss:
    """Sentinel: treat this key as a cache miss."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "CodecMiss"


CODEC_MISS = CodecMiss()


def encode(value: Any) -> str:
    """Serialize a Python value to a Redis string."""
    return json.dumps(value, default=str, separators=(",", ":"))


def decode(raw: Any) -> Any | CodecMiss:
    """
    Deserialize a Redis string.

    Returns ``CODEC_MISS`` for missing, empty, or undecodable values so callers
    can drop a single bad key without failing the whole batch.
    """
    if raw is None:
        return CODEC_MISS
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("cache_codec_decode_bytes_failed")
            return CODEC_MISS
    if not isinstance(raw, str):
        return raw
    if raw == "":
        return CODEC_MISS
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("cache_codec_decode_miss")
        return CODEC_MISS
