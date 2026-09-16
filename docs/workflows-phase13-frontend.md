# Workflow Domain — Phase 13 (Simple Frontend)

Ops UI without React Flow — list / vertical editor / automations / runs.

## Routes

| Path | Page |
|------|------|
| `/dashboard/workflows` | list + create |
| `/dashboard/workflows/:definitionId` | vertical step editor |
| `/dashboard/automations` | bind workflow + brand + targets + schedule |
| `/dashboard/runs` | run list (polls) |
| `/dashboard/runs/:runId` | node timeline + resume/advance |

Reuse `/dashboard/accounts` + `/dashboard/brand-profile` (no brands CRUD UI).

## Backend added

Automation HTTP under `/api/v1/workflows`:

* `GET/POST /automations`, `GET/PATCH /automations/{id}`
* `GET /brands` — picker options from `Brand` rows

Editor uses existing definition APIs: draft `PUT`, `validate-graph`, `publish`, `runs`, `resume`, `advance`.

## Frontend

* `api/workflows.ts` + `api/workflowTypes.ts`
* query keys `queryKeyFactories.workflows.*`
* nav: Workflows / Automations / Runs
* features: linear graph helpers + step list / config panels

Editor: linear step list, JSON config per node, account targets, validate / publish / test-run.

## Non-goals

* React Flow canvas (Phase 14)
* Full JSON-schema form generation
* Archive/duplicate endpoints
