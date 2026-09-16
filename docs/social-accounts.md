# Social accounts

External destination accounts for publishing and workflow targeting. Independent from Brand; linked via `BrandSocialAccount`.

## Concepts

| Entity | Role |
|--------|------|
| `SocialAccount` | Platform identity + encrypted tokens (`SocialAccountToken`) |
| `BrandSocialAccount` | Brand ↔ account M2M + generation/publishing overrides |
| `AutomationTarget` | Automation ↔ account + per-run overrides |

Workflow graphs and UI refer to **`social_account_id` only** — never OAuth/refresh tokens.

## Capability model

Typed `PlatformCapabilities` (`backend/modules/publishing/platform_capabilities.py`):

* booleans: text / images / video / audio / threads / native scheduling  
* limits: max text length, images, video duration/size, formats  
* `provider_id` string (not a global brittle enum)

Compiler maps capabilities → workflow tags (`video`, `image`, `tts`, `publish`, …) and rejects incompatible graphs before expensive generation.

Detail: [workflows-phase10-platform-capabilities.md](workflows-phase10-platform-capabilities.md).

## Canonical content → platforms

Prefer shared generation then late specialization:

```text
Research / generate canonical
        ↓
  platform_transform (per account)
        ↓
     publish jobs
```

Avoid N full pipelines for N accounts of the same brand.

## Adding a social provider

1. Implement provider adapter under `backend/modules/publishing/` conforming to `provider_base` (`validate_auth`, `create_draft`, `publish_now`, …).
2. Register in provider registry (`get_provider` / platform string id).
3. Add `PlatformCapabilities` defaults for the provider id.
4. Ensure token storage uses encrypted `SocialAccountToken` — never workflow JSON.
5. Wire UI account connect/select if needed; expose `social_account_id` to workflows.
6. Add capability + publish dry-run tests; keep production publish dry-run unless explicitly changing policy.

## Security

* Tenant isolation on every account query.
* Audit: `publishing.account_upserted` on upsert.
* Frontend workflow config must not receive credentials.

## Related

* [workflows.md](workflows.md)
* [automations.md](automations.md)
* [workflows-phase17-security.md](workflows-phase17-security.md)
