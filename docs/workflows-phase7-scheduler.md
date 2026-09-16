# Workflow Domain — Phase 7 (Automation Scheduler)

DB-backed schedules. Celery Beat only ticks once/minute — no per-automation Beat entries.

## Flow

```text
Celery Beat (every minute)
  → tick_due_automations_task
    → SELECT due automations FOR UPDATE SKIP LOCKED
    → INSERT automation_occurrences (UNIQUE automation_id + scheduled_occurrence)
    → WorkflowEngine.start_run(trigger_type=schedule, advance=False)
    → advance_workflow_run_task.delay(...)
    → bump next_run_at / last_run_at
  → (later) WorkflowRun terminal → occurrence SUCCEEDED / FAILED / SKIPPED
```

## trigger_config

| kind | fields |
|------|--------|
| `interval` | `every_seconds` (≥60) |
| `daily` | `at` (`HH:MM`) |
| `weekly` | `days` (`mon`…`sun`), `at` |
| `cron` | `expr` (croniter) |

Timezone: `Automation.timezone` (IANA). `next_run_at` stored UTC.

## Lifecycle: `next_run_at` sync

`AutomationScheduler.sync_schedule_state` runs on create and on any update that
touches `enabled`, `trigger_type`, `trigger_config`, or `timezone`:

| State | `next_run_at` |
|-------|---------------|
| disabled | `null` |
| manual / webhook | `null` |
| schedule + enabled | recompute from **now** |

Recompute always uses `after=now`, so re-enable / timezone / config changes never
fire an obsolete historical slot that was left in the past.

## DST policy (`Europe/Brussels` and other IANA zones)

Wall-clock mapping via `combine_local_wall_time`:

* **Nonexistent** (spring forward gap, e.g. 02:30 on 2026-03-29): advance
  minute-by-minute to the first valid local time after the gap (typically 03:00).
* **Ambiguous** (autumn overlap, e.g. 02:30 on 2026-10-25): prefer `fold=0`
  (the earlier occurrence).

Applies to daily, weekly, and cron schedules after croniter yields a local time.

## Occurrence lifecycle

```text
CLAIMED → STARTED → SUCCEEDED | FAILED | SKIPPED
                  ↘ FAILED (start error)
CLAIMED duplicate → SKIPPED (UNIQUE conflict)
```

When the linked `WorkflowRun` reaches a terminal status, `sync_occurrence_for_run`
maps:

* run `succeeded` → occurrence `succeeded`
* run `failed` → occurrence `failed`
* run `cancelled` → occurrence `skipped`

## Idempotency

* `UNIQUE(automation_id, scheduled_occurrence)`
* Run `correlation_id = sched:{automation_id}:{occurrence_key}`
* Duplicate tick of same slot → occurrence skip + still advance `next_run_at`
* `claim_due_automations` uses `SELECT … FOR UPDATE SKIP LOCKED` on `automations` rows (locks held until tick transaction ends)

## Crash-loop fix (ops Phase 4)

Missing tables caused Celery `tick_due_automations_task` to error-loop. Schema must be at Alembic head (see [`schema-drift-protection.md`](schema-drift-protection.md)). The task does **not** swallow `UndefinedTableError` / `ProgrammingError`.

Tests: `test_workflow_scheduler.py`, `test_workflow_phase7_scheduler_lifecycle.py`, `test_workflow_scheduler_pg.py` (`CG_RUN_PG_SCHEDULER=1`).

## Modules

* `schedule_config.py` / `schedule_next.py`
* `scheduler_repository.py` / `scheduler.py` / `occurrence_sync.py`
* `automation_occurrences` migration `f2a3b4c5d6e7`
* Celery: `tick_due_automations_task`, `advance_workflow_run_task`

## Next

Phase 8 — configuration precedence resolver.
