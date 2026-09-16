# Chess configuration (Phase 30)

All chess provider and engine settings live in **backend** settings
(`backend/core/config.py`) and are documented in `backend/.env.example`.

Do **not** expose provider tokens or engine paths through Vite / client env.
The frontend talks to SignalForge APIs only (`VITE_API_BASE`).

## Variables actually used

| Variable | Default | Role |
|----------|---------|------|
| `LICHESS_API_TOKEN` | empty | Optional Bearer for Lichess explorer / API |
| `LICHESS_API_BASE_URL` | `https://lichess.org` | Puzzle + site API host |
| `LICHESS_EXPLORER_BASE_URL` | `https://explorer.lichess.org` | Masters explorer host |
| `LICHESS_HTTP_TIMEOUT_SECONDS` | `20` | Lichess HTTP read timeout |
| `LICHESS_HTTP_MAX_RETRIES` | `2` | Lichess HTTP retries |
| `LICHESS_RATE_LIMIT_RPH` | `60` | Soft client-side requests/hour |
| `CHESSCOM_API_BASE_URL` | `https://api.chess.com` | Chess.com PubAPI |
| `CHESSCOM_USER_AGENT` | SignalForge… | Required fair-use identity |
| `CHESSCOM_HTTP_TIMEOUT_SECONDS` | `20` | Chess.com HTTP read timeout |
| `CHESSCOM_HTTP_MAX_RETRIES` | `2` | Chess.com HTTP retries |
| `CHESSCOM_RATE_LIMIT_RPH` | `60` | Soft client-side requests/hour |
| `HTTP_PROVIDER_LICHESS_CONCURRENCY` | `2` | Shared `core.http` budget |
| `HTTP_PROVIDER_CHESSCOM_CONCURRENCY` | `2` | Shared `core.http` budget |
| `CHESS_CACHE_*_TTL_SECONDS` | see `.env.example` | Provider response cache TTLs |
| `STOCKFISH_PATH` | empty | Path to Stockfish binary |
| `CHESS_ENGINE_DEPTH` | `12` | Default analysis depth |
| `CHESS_ENGINE_TIME_LIMIT` | empty | Optional seconds per position |
| `CHESS_ENGINE_HASH_MB` | `64` | UCI Hash |
| `CHESS_ENGINE_THREADS` | `1` | UCI Threads |
| `CHESS_SCHEDULE_DAILY_PUZZLE_ENABLED` | `true` | Beat: daily puzzle fanout |
| `CHESS_SCHEDULE_DAILY_PUZZLE_HOUR` / `_MINUTE` | `0` / `20` | UTC-ish Celery TZ crontab |
| `CHESS_SCHEDULE_PROVIDER_SYNC_ENABLED` | `false` | Beat: recent masters sync |
| `CHESS_SCHEDULE_PROVIDER_SYNC_HOUR` / `_MINUTE` | `6` / `30` | Daily crontab when interval unset |
| `CHESS_SCHEDULE_PROVIDER_SYNC_EVERY_MINUTES` | empty | Optional tournament cadence (§26) |
| `CHESS_SCHEDULE_PROVIDER_SYNC_PROVIDER` | `lichess_masters` | Fanout provider |
| `CHESS_SCHEDULE_PROVIDER_SYNC_MAX_GAMES` | `15` | Cap per sync run |
| `CHESS_DISCOVERY_AUTO_ANALYZE_ENABLED` | `false` | §21: enqueue Stockfish after provider_sync eligibility |
| `CHESS_DISCOVERY_AUTO_ANALYZE_MIN_RATING` | `2400` | Cheap rating gate (max side) |
| `CHESS_DISCOVERY_AUTO_ANALYZE_REQUIRE_NOTABLE_EVENT` | `false` | Require notable event name |
| `CHESS_DISCOVERY_AUTO_ANALYZE_EVENT_WHITELIST` | empty | Comma-separated event substrings |
| `CHESS_DISCOVERY_AUTO_ANALYZE_MAX_PER_SYNC` | `5` | Cap analyses per sync run |

## Not used (intentionally)

| Suggested in prompt | Why omitted |
|---------------------|-------------|
| `CHESS_PROVIDER_TIMEOUT_SECONDS` | Timeouts are per provider (`LICHESS_HTTP_TIMEOUT_SECONDS`, `CHESSCOM_HTTP_TIMEOUT_SECONDS`) |

## Client safety

Forbidden in `frontend/.env*`, `frontend/src/**`, and `VITE_*` names:

- `LICHESS_API_TOKEN`
- Chess.com credentials (none today; keep it that way)
- `STOCKFISH_PATH` / engine knobs as client secrets

Guard: `backend/tests/test_chess_configuration.py`.

## Local setup sketch

```bash
# backend/.env (copy from .env.example)
LICHESS_API_TOKEN=          # optional
STOCKFISH_PATH=/usr/bin/stockfish   # or brew path
CHESS_ENGINE_DEPTH=12

# frontend/.env — API base only
VITE_API_BASE=http://localhost:8000/api/v1
```
