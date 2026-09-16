# Chess observability (Phase 31 / §20)

Structured logs + domain metrics for chess catalog / engine / video handoff.
Provider HTTP latency and failures also flow through shared ``cg.provider.*``
(from ``backend/core/http.py``).

## Discovery + persistence counters (§20)

Every catalog import / provider-sync job ``result`` exposes (plus legacy aliases):

```text
discovered fetched parsed normalized
new_games existing_games new_sources duplicate_sources
skipped invalid persisted failed
duration_ms high_water_mark   # sync jobs
```

Analysis follow-on (when present):

```text
analysis_requested analysis_reused analysis_started
analysis_completed analysis_failed
critical_moments content_opportunities_created
```

§21 provider_sync extras: `auto_analyze`, `analysis_skipped_ineligible`, `sets_famous=false`.

Provider telemetry: request count / latency / retries / rate-limits / failures via
``cg.provider.*`` + ``chess_provider_request`` logs; sync jobs also record
``duration_ms`` and checkpoint ``high_water_mark``.

**Never** log full PGNs, tokens, or secrets (`sanitize_log_payload`).

## Structured log events

| Event | When |
|-------|------|
| `chess_provider_request` | Lichess / Chess.com HTTP attempt (action, outcome, duration_ms, status_class) |
| `chess_discovery_persistence` | Catalog job summary with §20 counters |
| `chess_game_import_done` | PGN archive import finished (inserted / linked / duplicates / invalid) |
| `chess_puzzle_import_done` | Puzzle CSV import finished |
| `chess_analysis_lifecycle` | requested / reused / started / completed / failed |
| `chess_engine_analysis` | Stockfish job completed |
| `chess_engine_failure` | Stockfish config or runtime failure |
| `chess_video_handoff` | Catalog/paste/famous game → video job (queued or cache hit) |

Never log tokens, PGN bodies, or tenant ids on metric labels. Correlation stays on structlog / request context.

## Metrics

| Series | Attrs | Answers |
|--------|-------|---------|
| `cg.provider.request.total` / `duration_ms` | `provider`, `outcome`, `status_class` | Which provider is failing? Latency? |
| `cg.chess.import.total` | `operation`, `provider`, `result` | Import / duplicate / invalid / handoff / analysis enqueue |
| `cg.operation.*` `operation=chess.catalog.discovery` | `outcome` | Discovery/persist job duration |
| `cg.operation.*` `operation=chess.analysis.enqueue` | `outcome` | Analysis requested vs reused |
| `cg.operation.total` / `duration_ms` `operation=chess.engine.analyze` | `outcome`, `error_class` | How long does Stockfish take? Failures? |
| `cg.operation.*` `operation=chess.video.handoff` | `outcome` | Catalog → content creation volume |
| `cg.publish.attempt.total` | `platform`, `outcome`, `post_type` | Successful posts (join to chess via job `chess_game_id` in logs/DB, not labels) |

Import `result` values: `inserted`, `linked`, `duplicate`, `invalid`, `filtered`, `queued`, `cached`, `requested`, `reused`.

Handoff `provider` (source) values: `catalog`, `famous`, `paste`.

## Operator questions → signals

| Question | Look at |
|----------|---------|
| How many games did we import? | `cg.chess.import.total{operation=chess.game.import,result=inserted}` or job `result.new_games` |
| How many were duplicates? | `result=duplicate` (+ `linked` / `new_sources`) |
| Which provider is failing? | `cg.provider.request.total{outcome=failure\|transport_error}` + `chess_provider_request` logs |
| How long does Stockfish take? | `cg.operation.duration_ms{operation=chess.engine.analyze}` |
| Analysis reuse rate? | `chess.analysis.enqueue` `result=reused` vs `requested` |
| Sync checkpoint? | job `result.high_water_mark` + `chess_discovery_persistence` |
| How many imported games became content? | `cg.chess.import.total{operation=chess.video.handoff,provider=catalog\|famous}` |

Snapshot: `GET /api/v1/health/metrics` → `domain.counters` / histograms.

Implementation: `backend/modules/chess_intelligence/observability.py`.
