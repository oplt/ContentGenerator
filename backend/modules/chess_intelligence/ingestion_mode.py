"""Hybrid chess ingestion lifecycle modes (application-level, not DB enums).

Distinct from ``source_rules.IntegrationMode`` (how a provider may be contacted).
These modes answer *why* data enters the local catalog.

All game paths converge on::

    raw / provider input → normalize → fingerprint → dedupe → ChessGame + ChessGameSource

Puzzle paths converge on normalize → fingerprint → puzzle repository upsert.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.modules.chess_intelligence.catalog_job_models import ChessCatalogJobKind


class ChessIngestionMode(str, Enum):
    """Four hybrid lifecycle modes for catalog ingress."""

    HISTORICAL_BOOTSTRAP = "historical_bootstrap"
    RECENT_DISCOVERY = "recent_discovery"
    PUZZLE_SYNC = "puzzle_sync"
    MANUAL_IMPORT = "manual_import"


METADATA_KEY = "ingestion_mode"


@dataclass(frozen=True, slots=True)
class IngestionModeProfile:
    """Behavioral contract for one lifecycle mode."""

    mode: ChessIngestionMode
    purpose: str
    bulk_oriented: bool
    incremental: bool
    scheduled: bool
    checkpointed: bool
    requires_live_http_after_import: bool
    reads_local_catalog: bool


MODE_PROFILES: dict[ChessIngestionMode, IngestionModeProfile] = {
    ChessIngestionMode.HISTORICAL_BOOTSTRAP: IngestionModeProfile(
        mode=ChessIngestionMode.HISTORICAL_BOOTSTRAP,
        purpose="build a durable local library of important historical games",
        bulk_oriented=True,
        incremental=False,
        scheduled=False,
        checkpointed=False,
        requires_live_http_after_import=False,
        reads_local_catalog=True,
    ),
    ChessIngestionMode.RECENT_DISCOVERY: IngestionModeProfile(
        mode=ChessIngestionMode.RECENT_DISCOVERY,
        purpose="discover newly available master/notable games",
        bulk_oriented=False,
        incremental=True,
        scheduled=True,
        checkpointed=True,
        requires_live_http_after_import=False,
        reads_local_catalog=True,
    ),
    ChessIngestionMode.PUZZLE_SYNC: IngestionModeProfile(
        mode=ChessIngestionMode.PUZZLE_SYNC,
        purpose="refresh puzzle content asynchronously",
        bulk_oriented=True,
        incremental=True,
        scheduled=True,
        checkpointed=False,
        requires_live_http_after_import=False,
        reads_local_catalog=True,
    ),
    ChessIngestionMode.MANUAL_IMPORT: IngestionModeProfile(
        mode=ChessIngestionMode.MANUAL_IMPORT,
        purpose="operator PGN/API/editorial import through canonical normalization",
        bulk_oriented=False,
        incremental=False,
        scheduled=False,
        checkpointed=False,
        requires_live_http_after_import=False,
        reads_local_catalog=True,
    ),
}


# Catalog job kinds that ingest entity rows (not curation / analysis re-extract).
_JOB_KIND_TO_MODE: dict[str, ChessIngestionMode] = {
    ChessCatalogJobKind.PGN_IMPORT.value: ChessIngestionMode.HISTORICAL_BOOTSTRAP,
    ChessCatalogJobKind.PROVIDER_SYNC.value: ChessIngestionMode.RECENT_DISCOVERY,
    ChessCatalogJobKind.PUZZLE_IMPORT.value: ChessIngestionMode.PUZZLE_SYNC,
    ChessCatalogJobKind.DAILY_PUZZLE_SYNC.value: ChessIngestionMode.PUZZLE_SYNC,
}


def profile_for(mode: ChessIngestionMode) -> IngestionModeProfile:
    return MODE_PROFILES[mode]


def mode_for_catalog_job_kind(kind: str) -> ChessIngestionMode | None:
    """Map durable job kind → lifecycle mode; None for non-ingest jobs."""
    return _JOB_KIND_TO_MODE.get(kind)


def stamp_ingestion_mode(
    metadata: dict[str, Any] | None,
    mode: ChessIngestionMode,
) -> dict[str, Any]:
    """Return a copy of metadata with ``ingestion_mode`` set."""
    out = dict(metadata or {})
    out[METADATA_KEY] = mode.value
    return out


def ensure_job_params_mode(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """Stamp ``ingestion_mode`` on catalog job params when the kind ingests data."""
    mode = mode_for_catalog_job_kind(kind)
    if mode is None:
        return dict(params)
    return stamp_ingestion_mode(params, mode)
