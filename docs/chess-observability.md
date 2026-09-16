# Chess observability (Phase 31)

Structured logs + domain metrics for chess catalog / engine / video handoff.
Provider HTTP latency and failures also flow through shared ``cg.provider.*``
(from ``backend/core/http.py``).

## Structured log events

| Event | When |
|-------|------|
| `chess_provider_request` | Lichess / Chess.com HTTP attempt (action, outcome, duration_ms, status_class) |
| `chess_game_import_done` | PGN archive import finished (inserted / linked / duplicates / invalid) |
| `chess_puzzle_import_done` | Puzzle CSV import finished |
| `chess_engine_analysis` | Stockfish job completed |
| `chess_engine_failure` | Stockfish config or runtime failure |
| `chess_video_handoff` | Catalog/paste/famous game → video job (queued or cache hit) |

Never log tokens, PGN bodies, or tenant ids on metric labels. Correlation stays on structlog / request context.

## Metrics

| Series | Attrs | Answers |
|--------|-------|---------|
| `cg.provider.request.total` / `duration_ms` | `provider`, `outcome`, `status_class` | Which provider is failing? Latency? |
| `cg.chess.import.total` | `operation`, `provider`, `result` | Import / duplicate / invalid / handoff counts |
| `cg.operation.total` / `duration_ms` `operation=chess.engine.analyze` | `outcome`, `error_class` | How long does Stockfish take? Failures? |
| `cg.operation.*` `operation=chess.video.handoff` | `outcome` | Catalog → content creation volume |
| `cg.publish.attempt.total` | `platform`, `outcome`, `post_type` | Successful posts (join to chess via job `chess_game_id` in logs/DB, not labels) |

Import `result` values: `inserted`, `linked`, `duplicate`, `invalid`, `filtered`, `queued`, `cached`.

Handoff `provider` (source) values: `catalog`, `famous`, `paste`.

## Operator questions → signals

| Question | Look at |
|----------|---------|
| How many games did we import? | `cg.chess.import.total{operation=chess.game.import,result=inserted}` |
| How many were duplicates? | `result=duplicate` (+ `linked` for source merges) |
| Which provider is failing? | `cg.provider.request.total{outcome=failure\|transport_error}` + `chess_provider_request` logs |
| How long does Stockfish take? | `cg.operation.duration_ms{operation=chess.engine.analyze}` |
| How many imported games became content? | `cg.chess.import.total{operation=chess.video.handoff,provider=catalog\|famous}` |
| Which game types produce successful posts? | Handoff source mix + publish outcomes; famous vs catalog via `chess_video_handoff.is_famous` logs / DB |

Snapshot: `GET /api/v1/health/metrics` → `domain.counters` / histograms.

Implementation: `backend/modules/chess_intelligence/observability.py`.
