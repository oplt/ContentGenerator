# Dry-Run Publishing Examples

## Default Safety Setting

Keep dry-run enabled in local and staging environments:

```bash
export SOCIAL_DRY_RUN_BY_DEFAULT=true
```

## Queue a Dry-Run Publish

```bash
curl -X POST http://localhost:8000/api/v1/publishing/publish-now \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <access-token>' \
  -d '{
    "content_job_id": "00000000-0000-0000-0000-000000000001",
    "platforms": ["x", "bluesky"],
    "dry_run": true,
    "idempotency_key": "dryrun-brief-001"
  }'
```

## Validate a Connected Account Without Publishing

```bash
curl -X POST http://localhost:8000/api/v1/publishing/connected-accounts/<connected-account-id>/validate \
  -H 'Authorization: Bearer <access-token>'
```

## What to Expect

- Jobs move through the queue and provider adapters exactly as they would for a live publish.
- No live social post should be created when `dry_run=true`.
- Queue payloads, retries, and recovery actions remain visible in the admin UI.
