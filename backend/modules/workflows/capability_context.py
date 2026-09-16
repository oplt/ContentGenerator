"""Build / enrich CompileContext capability maps (Phase 8 + 10).

Runtime truth always comes from SocialAccount rows. Client-supplied capability
maps are ignored for execution. Design-time simulation may use hypothetical caps
via ``DesignValidationContext`` / ``apply_design_validation_context``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.models import SocialAccount, SocialAccountStatus
from backend.modules.publishing.platform_capabilities import (
    DEFAULT_RUNTIME_CAPABILITIES,
    PlatformCapabilities,
    flags_to_capabilities,
    workflow_capability_tags,
)
from backend.modules.workflows.graph_schema import (
    CompileContext,
    DesignValidationContext,
    RuntimeClientContext,
)
from backend.modules.workflows.security import authorize_social_account_ids

_RUNTIME_BLOCKED_STATUSES = {
    SocialAccountStatus.QUARANTINED.value,
    SocialAccountStatus.DISCONNECTED.value,
}


def capabilities_from_account(
    *,
    platform: str | None,
    capability_flags: dict[str, Any] | None,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> tuple[PlatformCapabilities, list[str]]:
    caps = flags_to_capabilities(capability_flags, platform=platform)
    tags = workflow_capability_tags(caps, runtime=runtime)
    return caps, tags


def merge_account_capability_maps(
    *,
    account_ids: list[UUID],
    platforms: dict[str, str],
    flag_maps: dict[str, dict[str, Any]],
    existing_tags: dict[str, list[str]] | None = None,
    runtime: list[str] | tuple[str, ...] | None = None,
    prefer_existing: bool = False,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Return (account_capabilities tags, account_platform_capabilities dumps).

    When ``prefer_existing`` is False (runtime), DB-derived tags always win.
    When True (design simulation), keep caller-supplied tags if present.
    """
    tags_out: dict[str, list[str]] = dict(existing_tags or {}) if prefer_existing else {}
    typed_out: dict[str, dict[str, Any]] = {}
    runtime_caps = runtime if runtime is not None else DEFAULT_RUNTIME_CAPABILITIES
    for account_id in account_ids:
        key = str(account_id)
        if prefer_existing and key in tags_out and key in typed_out:
            continue
        platform = platforms.get(key)
        flags = flag_maps.get(key)
        if not platform and not flags:
            continue
        caps, tags = capabilities_from_account(
            platform=platform,
            capability_flags=flags,
            runtime=runtime_caps,
        )
        typed_out[key] = caps.model_dump(mode="json")
        if not prefer_existing or key not in tags_out:
            tags_out[key] = tags
    return tags_out, typed_out


def enrich_compile_context(
    context: CompileContext,
    *,
    platforms: dict[str, str] | None = None,
    flag_maps: dict[str, dict[str, Any]] | None = None,
    typed_caps: dict[str, dict[str, Any]] | None = None,
    runtime: list[str] | tuple[str, ...] | None = None,
    prefer_existing: bool = False,
) -> CompileContext:
    """Fill capability maps from platform/flags.

    Runtime callers must pass ``prefer_existing=False`` so client maps cannot win.
    """
    if not context.social_account_ids:
        return context

    platforms = dict(platforms or context.account_platforms)
    flag_maps = dict(flag_maps or {})
    existing_typed = dict(context.account_platform_capabilities) if prefer_existing else {}
    if typed_caps:
        existing_typed.update(typed_caps)

    if prefer_existing:
        for key, dump in existing_typed.items():
            if key not in flag_maps and isinstance(dump, dict):
                raw = dump.get("raw_flags")
                if isinstance(raw, dict):
                    flag_maps[key] = dict(raw)
                if key not in platforms and dump.get("provider_id"):
                    platforms[key] = str(dump["provider_id"])

    tags, typed = merge_account_capability_maps(
        account_ids=list(context.social_account_ids),
        platforms=platforms,
        flag_maps=flag_maps,
        existing_tags=dict(context.account_capabilities) if prefer_existing else None,
        runtime=runtime,
        prefer_existing=prefer_existing,
    )
    if prefer_existing:
        for key, dump in existing_typed.items():
            typed[key] = dump

    return context.model_copy(
        update={
            "account_capabilities": tags,
            "account_platform_capabilities": typed,
            "account_platforms": platforms,
        }
    )


def apply_design_validation_context(
    context: DesignValidationContext | CompileContext | None,
) -> CompileContext:
    """Design-time: keep hypothetical capability maps (explicit simulation path)."""
    ctx = context or DesignValidationContext()
    if isinstance(ctx, DesignValidationContext):
        return CompileContext.model_validate(ctx.model_dump())
    return ctx


def client_context_to_seed(
    client: RuntimeClientContext | CompileContext | dict[str, Any] | None,
) -> CompileContext:
    """Strip any client-supplied capability maps; keep IDs + policy flags only."""
    if client is None:
        return CompileContext()
    if isinstance(client, RuntimeClientContext):
        return CompileContext(
            social_account_ids=list(client.social_account_ids),
            require_publish_targets=client.require_publish_targets,
            allow_multiple_triggers=client.allow_multiple_triggers,
            require_approval_before_publish=client.require_approval_before_publish,
            require_capability_check=client.require_capability_check,
        )
    if isinstance(client, dict):
        raw = dict(client)
        raw.pop("account_capabilities", None)
        raw.pop("account_platform_capabilities", None)
        raw.pop("account_platforms", None)
        raw.pop("account_statuses", None)
        try:
            rc = RuntimeClientContext.model_validate(raw)
        except Exception:  # noqa: BLE001
            ids = raw.get("social_account_ids") or []
            return CompileContext(
                social_account_ids=list(ids),
                require_publish_targets=bool(raw.get("require_publish_targets", True)),
                allow_multiple_triggers=bool(raw.get("allow_multiple_triggers", False)),
                require_approval_before_publish=bool(
                    raw.get("require_approval_before_publish", True)
                ),
                require_capability_check=bool(raw.get("require_capability_check", False)),
            )
        return client_context_to_seed(rc)
    # CompileContext from internal callers — still strip maps for runtime seed.
    return CompileContext(
        social_account_ids=list(client.social_account_ids),
        require_publish_targets=client.require_publish_targets,
        allow_multiple_triggers=client.allow_multiple_triggers,
        require_approval_before_publish=client.require_approval_before_publish,
        require_capability_check=client.require_capability_check,
    )


def _maps_from_accounts(
    accounts: list[SocialAccount],
    *,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]], dict[str, str]]:
    platforms: dict[str, str] = {}
    flags: dict[str, dict[str, Any]] = {}
    statuses: dict[str, str] = {}
    for account in accounts:
        key = str(account.id)
        platforms[key] = account.platform
        flags[key] = dict(account.capability_flags or {})
        statuses[key] = str(account.status)
    return platforms, flags, statuses


async def build_runtime_compile_context(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    client: RuntimeClientContext | CompileContext | dict[str, Any] | None = None,
    social_account_ids: list[UUID] | None = None,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> CompileContext:
    """Authoritative runtime context: IDs from client, capabilities from DB only."""
    seed = client_context_to_seed(client)
    ids = list(social_account_ids) if social_account_ids is not None else list(seed.social_account_ids)
    seed = seed.model_copy(update={"social_account_ids": ids})

    if not ids:
        return seed.model_copy(
            update={
                "account_capabilities": {},
                "account_platform_capabilities": {},
                "account_platforms": {},
                "account_statuses": {},
            }
        )

    await authorize_social_account_ids(db, tenant_id=tenant_id, social_account_ids=ids)

    from backend.modules.publishing.repository import PublishingRepository

    accounts = await PublishingRepository(db).get_social_accounts_by_ids(tenant_id, ids)
    # Defense: reject disconnected for runtime (quarantine already denied).
    blocked = [
        str(a.id)
        for a in accounts
        if a.status in _RUNTIME_BLOCKED_STATUSES
    ]
    if blocked:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=(
                "Social accounts are quarantined or disconnected and cannot be "
                f"used at runtime: {', '.join(blocked)}"
            ),
        )

    platforms, flags, statuses = _maps_from_accounts(accounts, runtime=runtime)
    enriched = enrich_compile_context(
        seed,
        platforms=platforms,
        flag_maps=flags,
        runtime=runtime,
        prefer_existing=False,
    )
    return enriched.model_copy(update={"account_statuses": statuses})


async def enrich_compile_context_from_db(
    db: AsyncSession,
    context: CompileContext | None,
    *,
    tenant_id: UUID,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> CompileContext:
    """Back-compat: always rebuild capability maps from DB (never trust client maps)."""
    return await build_runtime_compile_context(
        db,
        tenant_id=tenant_id,
        client=context,
        runtime=runtime,
    )
