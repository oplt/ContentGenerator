# Phase 7 — Harden Scheduler Lifecycle

## End state

* `AutomationScheduler.sync_schedule_state` deterministically updates `next_run_at`
  when enabled / trigger type / config / timezone change
* Disabled and non-schedule triggers clear `next_run_at`
* Re-enable / config / tz always recompute from **now** (no obsolete historical fire)
* DST policy documented and tested for Europe/Brussels spring + autumn
* Occurrence statuses include `SUCCEEDED`; terminal WorkflowRun syncs occurrence state

## Files

* `schedule_next.py` — `combine_local_wall_time`, DST-safe daily/weekly/cron
* `scheduler.py` — `sync_schedule_state`
* `occurrence_sync.py` — `sync_occurrence_for_run`
* `automation_service.py` — create/update call sync
* `engine.py` / `engine_node_task.py` / `engine_resume.py` — sync after finalize
* Docs: `docs/workflows-phase7-scheduler.md`

## Tests

```bash
cd backend && pytest -q \
  tests/test_workflow_phase7_scheduler_lifecycle.py \
  tests/test_workflow_scheduler.py \
  tests/test_workflow_production_gaps.py -k 'scheduler or occurrence or sync_schedule'
```
