# Caching architecture (Phase 5)

## Key format

`cg:{env}:{tenant_id|global}:{owner}:{identity}[:v{version}]`

## Owners

| Owner | Purpose | Invalidation |
|-------|---------|--------------|
| `content_strategy` | Brand/plan snapshots | Mutating strategy repository methods |
| `identity` | User/membership lookups | Identity repository mutations |
| `ingestion` | Source fetch success cache | Source delete / successful refresh overwrite |
| `auth_token` | Opaque verify/reset tokens (via RedisCache codec) | Consume-on-use delete |
| `robots` | robots.txt per origin | TTL expiry |
| `oauth` | Provider access tokens (no logging of secrets) | TTL near token expiry + single-flight refresh |
| `chess_intelligence` | Lichess/Chess.com provider HTTP DTOs (global scope) | TTL expiry (see Phase 22) |

## Rules

* Application cache uses shared `cache_codec.encode/decode`.
* Never `FLUSHALL` — use `RedisCache.flush_namespace()` (`cg:{env}:*`).
* Prefer separate Redis URLs/DBs: `REDIS_CACHE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
* Distributed single-flight: Redis `SET NX PX` + token-safe unlock.
* Process-local static assets: `backend.core.static_cache` (`lru_cache`).

## Chess provider cache (Phase 22)

Owner: `chess_intelligence` via `providers/provider_cache.py` (TenantCache, **global** keys — payloads are not tenant-specific).

| Payload | Key identity | Default TTL |
|---------|--------------|-------------|
| Masters search | `lichess_masters:search:{digest}` | `CHESS_CACHE_MASTERS_SEARCH_TTL_SECONDS` (30m) |
| Game PGN | `{provider}:pgn:{external_id}` | `CHESS_CACHE_GAME_PGN_TTL_SECONDS` (7d) |
| Individual puzzle | `{provider}:puzzle:{id}` | `CHESS_CACHE_PUZZLE_TTL_SECONDS` (7d) |
| Daily puzzle | `{provider}:daily:{YYYY-MM-DD}` | min(next UTC midnight+5m, `CHESS_CACHE_DAILY_PUZZLE_TTL_SECONDS`) |
| Provider metadata | `{provider}:meta:{kind}:{id}` | `CHESS_CACHE_PROVIDER_META_TTL_SECONDS` (1h) |
| Chess.com month archive | `chesscom:month:{user}:{YYYY}:{MM}` | same as game PGN |

Canonical catalog rows win: `ChessCatalogService.get_game` / `get_puzzle` never call providers; `catalog_prefer.get_external_game_prefer_catalog` short-circuits when `source_provider` + `source_external_id` already exist.
