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
```

## trigger_config

| kind | fields |
|------|--------|
| `interval` | `every_seconds` (≥60) |
| `daily` | `at` (`HH:MM`) |
| `weekly` | `days` (`mon`…`sun`), `at` |
| `cron` | `expr` (croniter) |

Timezone: `Automation.timezone` (IANA). `next_run_at` stored UTC.

## Idempotency

* `UNIQUE(automation_id, scheduled_occurrence)`
* Run `correlation_id = sched:{automation_id}:{occurrence_key}`
* Duplicate tick of same slot → occurrence skip + still advance `next_run_at`

## Modules

* `schedule_config.py` / `schedule_next.py`
* `scheduler_repository.py` / `scheduler.py`
* `automation_occurrences` migration `f2a3b4c5d6e7`
* Celery: `tick_due_automations_task`, `advance_workflow_run_task`

## Next

Phase 8 — configuration precedence resolver.
