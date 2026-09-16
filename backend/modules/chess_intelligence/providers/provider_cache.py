"""Chess provider HTTP response cache via TenantCache (Phase 22).

Provider payloads are global (not tenant-specific). Canonical catalog rows still
win when present — callers should prefer DB before refetching PGN.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from pydantic import BaseModel

from backend.core.config import settings
from backend.core.tenant_cache import (
    OWNER_CHESS,
    CachePolicy,
    build_cache_key,
    tenant_cache,
)

T = TypeVar("T", bound=BaseModel)

_POLICY_SEARCH = CachePolicy(
    owner=OWNER_CHESS,
    ttl_seconds=int(settings.CHESS_CACHE_MASTERS_SEARCH_TTL_SECONDS),
    negative_ttl_seconds=120,
    ttl_jitter_seconds=30,
    singleflight=False,
)
_POLICY_PGN = CachePolicy(
    owner=OWNER_CHESS,
    ttl_seconds=int(settings.CHESS_CACHE_GAME_PGN_TTL_SECONDS),
    negative_ttl_seconds=300,
    ttl_jitter_seconds=60,
    singleflight=False,
)
_POLICY_PUZZLE = CachePolicy(
    owner=OWNER_CHESS,
    ttl_seconds=int(settings.CHESS_CACHE_PUZZLE_TTL_SECONDS),
    negative_ttl_seconds=300,
    ttl_jitter_seconds=60,
    singleflight=False,
)
_POLICY_META = CachePolicy(
    owner=OWNER_CHESS,
    ttl_seconds=int(settings.CHESS_CACHE_PROVIDER_META_TTL_SECONDS),
    negative_ttl_seconds=60,
    ttl_jitter_seconds=30,
    singleflight=False,
)


def daily_puzzle_ttl_seconds(*, now: datetime | None = None) -> int:
    """Expire near next UTC midnight (Lichess daily rotation), capped by settings."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    next_midnight = (current + timedelta(days=1)).replace(
        hour=0, minute=5, second=0, microsecond=0
    )
    until = int((next_midnight - current).total_seconds())
    ceiling = int(settings.CHESS_CACHE_DAILY_PUZZLE_TTL_SECONDS)
    return max(60, min(until, ceiling))


def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def key_masters_search(query_payload: dict[str, object]) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"lichess_masters:search:{_digest(query_payload)}",
        global_scope=True,
    )


def key_game_pgn(*, provider: str, external_id: str) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"{provider}:pgn:{external_id.strip().lower()}",
        global_scope=True,
    )


def key_puzzle(*, provider: str, puzzle_id: str) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"{provider}:puzzle:{puzzle_id.strip()}",
        global_scope=True,
    )


def key_daily_puzzle(*, provider: str, day_utc: str) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"{provider}:daily:{day_utc}",
        global_scope=True,
    )


def key_provider_meta(*, provider: str, kind: str, identity: str) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"{provider}:meta:{kind}:{identity.strip().lower()}",
        global_scope=True,
    )


def key_month_archive(*, provider: str, username: str, year: int, month: int) -> str:
    return build_cache_key(
        owner=OWNER_CHESS,
        identity=f"{provider}:month:{username.strip().lower()}:{year:04d}:{month:02d}",
        global_scope=True,
    )


async def cached_model(
    *,
    key: str,
    policy: CachePolicy,
    model_type: type[T],
    factory: Callable[[], Awaitable[T]],
    ttl_seconds: int | None = None,
) -> T:
    """get_or_set a Pydantic model as JSON via TenantCache."""

    async def _fill() -> dict[str, object]:
        value = await factory()
        return value.model_dump(mode="json")

    if ttl_seconds is not None:
        policy = CachePolicy(
            owner=policy.owner,
            ttl_seconds=ttl_seconds,
            negative_ttl_seconds=policy.negative_ttl_seconds,
            fail_mode=policy.fail_mode,
            forbid_credentials=policy.forbid_credentials,
            singleflight=policy.singleflight,
            swr_seconds=policy.swr_seconds,
            ttl_jitter_seconds=policy.ttl_jitter_seconds,
        )

    payload = await tenant_cache.get_or_set(key, policy=policy, factory=_fill)
    assert payload is not None
    return model_type.model_validate(payload)


async def cached_json_list(
    *,
    key: str,
    policy: CachePolicy,
    factory: Callable[[], Awaitable[list[dict[str, object]]]],
) -> list[dict[str, object]]:
    payload = await tenant_cache.get_or_set(key, policy=policy, factory=factory)
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


# Exported policies for callers / tests
policy_search = _POLICY_SEARCH
policy_pgn = _POLICY_PGN
policy_puzzle = _POLICY_PUZZLE
policy_meta = _POLICY_META
