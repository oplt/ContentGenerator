"""Durable provider sync-state — resume cursor for a feed (≠ job execution history).

``ChessCatalogJob`` = one run.
``ChessProviderSyncState`` = where the logical feed should resume next time.

Catalog rows are tenant-partitioned, so sync state is tenant-scoped too: each tenant
owns its own high-water mark for discovery into *its* catalog.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChessProviderSyncState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Long-lived synchronization checkpoint for one provider feed per tenant."""

    __tablename__ = "chess_provider_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "sync_key",
            name="uq_chess_provider_sync_tenant_provider_key",
        ),
        Index("ix_chess_provider_sync_tenant_id", "tenant_id"),
        Index("ix_chess_provider_sync_tenant_provider", "tenant_id", "provider"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    # Stable feed identity within provider (e.g. "masters_default", "chesscom:hikaru").
    sync_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # Hash of normalized query identity (moves/fen/player/… — not the sliding year window).
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    high_water_mark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lookback_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86_400)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    state_metadata: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    last_error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_sync_query(params: dict[str, Any]) -> dict[str, Any]:
    """Canonical feed identity — excludes sliding year windows (those are incremental)."""
    keys = (
        "moves",
        "fen",
        "player",
        "white",
        "black",
        "sync_key",
    )
    out: dict[str, Any] = {}
    for key in keys:
        value = params.get(key)
        if value is None or value == "":
            continue
        out[key] = value
    return out


def compute_query_hash(params: dict[str, Any]) -> str:
    payload = json.dumps(normalize_sync_query(params), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_sync_key(*, provider: str, params: dict[str, Any]) -> str:
    explicit = str(params.get("sync_key") or "").strip()
    if explicit:
        return explicit[:128]
    player = str(params.get("player") or "").strip().lower()
    if provider == "chesscom" and player:
        return f"chesscom:{player}"[:128]
    return "default"


@dataclass(frozen=True, slots=True)
class SyncQueryWindow:
    """Bounded discovery window with intentional lookback overlap."""

    window_start: datetime
    window_end: datetime
    year_from: int
    year_to: int
    lookback_seconds: int
    high_water_mark_before: datetime | None
    bootstrap: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "year_from": self.year_from,
            "year_to": self.year_to,
            "lookback_seconds": self.lookback_seconds,
            "high_water_mark_before": (
                self.high_water_mark_before.isoformat() if self.high_water_mark_before else None
            ),
            "bootstrap": self.bootstrap,
        }


def compute_incremental_window(
    *,
    high_water_mark: datetime | None,
    lookback_seconds: int,
    now: datetime | None = None,
    bootstrap_lookback_seconds: int | None = None,
    explicit_year_from: int | None = None,
    explicit_year_to: int | None = None,
) -> SyncQueryWindow:
    """HWM − lookback → now (overlap intentional). First run uses a bounded bootstrap.

    Explicit year_* clamp the derived years when operators narrow/widen the search.
    """
    end = now or _utcnow()
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    lookback = max(0, int(lookback_seconds))
    bootstrap = high_water_mark is None
    if high_water_mark is not None:
        hwm = high_water_mark
        if hwm.tzinfo is None:
            hwm = hwm.replace(tzinfo=timezone.utc)
        start = hwm - timedelta(seconds=lookback)
    else:
        boot = int(
            bootstrap_lookback_seconds
            if bootstrap_lookback_seconds is not None
            else max(lookback, 7 * 86_400)
        )
        boot = max(lookback, min(boot, 365 * 86_400))
        start = end - timedelta(seconds=boot)
        hwm = None

    if start > end:
        start = end

    year_from = start.year
    year_to = end.year
    if explicit_year_from is not None:
        year_from = int(explicit_year_from)
    if explicit_year_to is not None:
        year_to = int(explicit_year_to)
    if year_from > year_to:
        year_from, year_to = year_to, year_from

    return SyncQueryWindow(
        window_start=start,
        window_end=end,
        year_from=year_from,
        year_to=year_to,
        lookback_seconds=lookback,
        high_water_mark_before=hwm,
        bootstrap=bootstrap,
    )


_GAME_DATE_RE = re.compile(r"^(\d{4})(?:[.\-/](\d{1,2})(?:[.\-/](\d{1,2}))?)?")


def parse_game_date(value: str | None) -> datetime | None:
    """Parse PGN-ish dates (YYYY, YYYY.MM, YYYY.MM.DD) as UTC midnight."""
    if not value:
        return None
    match = _GAME_DATE_RE.match(value.strip())
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def game_date_in_window(
    game_date: str | None,
    *,
    window: SyncQueryWindow,
    keep_unknown: bool = True,
) -> bool:
    """True if summary date overlaps the sync window (unknown dates kept by default)."""
    parsed = parse_game_date(game_date)
    if parsed is None:
        return keep_unknown
    # Inclusive bounds; year-only dates land on Jan 1 — lookback overlap covers edges.
    return window.window_start <= parsed <= window.window_end + timedelta(days=1)


class ChessProviderSyncStateService:
    """Load / create sync state; advance watermark only after safe completion."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(
        self,
        *,
        tenant_id: uuid.UUID,
        provider: str,
        params: dict[str, Any],
    ) -> ChessProviderSyncState:
        sync_key = default_sync_key(provider=provider, params=params)
        query_hash = compute_query_hash(params)
        lookback = int(params.get("lookback_seconds") or 86_400)
        lookback = max(0, min(lookback, 30 * 86_400))

        result = await self.db.execute(
            select(ChessProviderSyncState).where(
                ChessProviderSyncState.tenant_id == tenant_id,
                ChessProviderSyncState.provider == provider,
                ChessProviderSyncState.sync_key == sync_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            # Keep query_hash / lookback current when operator changes feed params.
            row.query_hash = query_hash
            if params.get("lookback_seconds") is not None:
                row.lookback_seconds = lookback
            return row

        row = ChessProviderSyncState(
            tenant_id=tenant_id,
            provider=provider,
            sync_key=sync_key,
            query_hash=query_hash,
            lookback_seconds=lookback,
            state_metadata={},
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def list_for_tenant(
        self, *, tenant_id: uuid.UUID
    ) -> list[ChessProviderSyncState]:
        """§33 inspect — durable checkpoints for the tenant (no provider I/O)."""
        rows = (
            await self.db.execute(
                select(ChessProviderSyncState)
                .where(ChessProviderSyncState.tenant_id == tenant_id)
                .order_by(
                    ChessProviderSyncState.provider.asc(),
                    ChessProviderSyncState.sync_key.asc(),
                )
            )
        ).scalars().all()
        return list(rows)

    async def mark_attempt(
        self,
        state: ChessProviderSyncState,
        *,
        job_id: uuid.UUID,
    ) -> None:
        state.last_attempt_at = _utcnow()
        state.last_job_id = job_id
        await self.db.flush()

    async def mark_success(
        self,
        state: ChessProviderSyncState,
        *,
        job_id: uuid.UUID,
        high_water_mark: datetime | None = None,
        cursor: str | None = None,
        state_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Advance durable resume point — call only when the run completed safely."""
        now = _utcnow()
        state.last_success_at = now
        state.last_attempt_at = state.last_attempt_at or now
        state.last_job_id = job_id
        state.last_error_summary = None
        state.high_water_mark = high_water_mark or now
        if cursor is not None:
            state.cursor = cursor
        if state_metadata:
            meta = dict(state.state_metadata or {})
            meta.update(state_metadata)
            state.state_metadata = meta
        await self.db.flush()

    async def mark_failure(
        self,
        state: ChessProviderSyncState,
        *,
        job_id: uuid.UUID,
        error_summary: str,
    ) -> None:
        """Record failure without advancing high_water_mark / cursor."""
        state.last_attempt_at = _utcnow()
        state.last_job_id = job_id
        state.last_error_summary = (error_summary or "")[:2000]
        await self.db.flush()
