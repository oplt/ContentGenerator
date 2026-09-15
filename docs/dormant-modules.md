# Dormant Feature Modules

**Decision date:** 2026-09-15  
**Roadmap task:** T1.2  
**Status:** Quarantined (not product-supported)

## Decision

Keep incomplete `platform`, `projects`, `profile`, `notifications`, `calendar`, and
`admin` code under `backend/modules/_dormant/` instead of activating or deleting it
in this release.

**T7.3 note (2026-09-15):** Quarantine retained. Deletion deferred until a product
decision retires these capabilities; contract tests still require the packages to
exist under `_dormant/` and stay unmounted.

| Module | Decision | Why |
|---|---|---|
| platform | quarantine | Broken settings/config contracts; no migrations/UI |
| projects | quarantine | Unmounted; no migrations/UI |
| profile | quarantine | Unmounted; users/identity cover active needs |
| notifications | quarantine | Unmounted; approvals/Telegram cover alerts |
| calendar | quarantine | Depends on dormant projects; no migrations/UI |
| admin | quarantine | Calls missing `AuditRepository.list_recent()`; live audit is `/api/v1/audit` |

## Hard rules

1. Do **not** `include_router` any `_dormant` router on `api_router`.
2. Do **not** import `_dormant` models into `backend/db/model_registry.py`.
3. Do **not** add Alembic revisions for dormant tables until a capability is completed.
4. Contract tests in `backend/tests/test_dormant_modules.py` enforce the above.
5. Reactivation checklist for one module:
   - fix broken contracts
   - additive migration matching models
   - register models
   - mount router with authz
   - OpenAPI + permission tests
   - frontend client/UI when user-facing
   - remove module from `DORMANT_MODULES` and mypy exclude only after green

## Related symbols

- Registry: `backend/core/dormant_modules.py`
- Live admin-only dep kept for dormant routers: `backend/api/deps/admin.py`
- Typecheck exclude: `modules/_dormant` in `backend/pyproject.toml` / `mypy.ini`
