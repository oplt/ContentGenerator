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

## Rules

* Application cache uses shared `cache_codec.encode/decode`.
* Never `FLUSHALL` — use `RedisCache.flush_namespace()` (`cg:{env}:*`).
* Prefer separate Redis URLs/DBs: `REDIS_CACHE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`.
* Distributed single-flight: Redis `SET NX PX` + token-safe unlock.
* Process-local static assets: `backend.core.static_cache` (`lru_cache`).
