"""Build / enrich CompileContext capability maps from accounts (Phase 10)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.publishing.platform_capabilities import (
    DEFAULT_RUNTIME_CAPABILITIES,
    PlatformCapabilities,
    flags_to_capabilities,
    workflow_capability_tags,
)
from backend.modules.workflows.graph_schema import CompileContext


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
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Return (account_capabilities tags, account_platform_capabilities dumps).

    Accounts without platform id and without flags stay unresolved (no invented caps).
    """
    tags_out: dict[str, list[str]] = dict(existing_tags or {})
    typed_out: dict[str, dict[str, Any]] = {}
    runtime_caps = runtime if runtime is not None else DEFAULT_RUNTIME_CAPABILITIES
    for account_id in account_ids:
        key = str(account_id)
        if key in tags_out and key in typed_out:
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
        if key not in tags_out:
            tags_out[key] = tags
    return tags_out, typed_out


def enrich_compile_context(
    context: CompileContext,
    *,
    platforms: dict[str, str] | None = None,
    flag_maps: dict[str, dict[str, Any]] | None = None,
    typed_caps: dict[str, dict[str, Any]] | None = None,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> CompileContext:
    """Fill missing capability maps from platform/flags without wiping explicit values."""
    if not context.social_account_ids:
        return context

    platforms = dict(platforms or context.account_platforms)
    flag_maps = dict(flag_maps or {})
    existing_typed = dict(context.account_platform_capabilities)
    if typed_caps:
        existing_typed.update(typed_caps)

    # Derive flags from typed dumps when only typed provided.
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
        existing_tags=dict(context.account_capabilities),
        runtime=runtime,
    )
    # Prefer already-provided typed dumps.
    for key, dump in existing_typed.items():
        typed[key] = dump

    return context.model_copy(
        update={
            "account_capabilities": tags,
            "account_platform_capabilities": typed,
            "account_platforms": platforms,
        }
    )


async def enrich_compile_context_from_db(
    db: AsyncSession,
    context: CompileContext | None,
    *,
    tenant_id: UUID,
    runtime: list[str] | tuple[str, ...] | None = None,
) -> CompileContext:
    ctx = context or CompileContext()
    if not ctx.social_account_ids:
        return ctx
    if ctx.account_capabilities and ctx.account_platform_capabilities:
        return ctx

    from backend.modules.publishing.repository import PublishingRepository

    accounts = await PublishingRepository(db).get_social_accounts_by_ids(
        tenant_id, list(ctx.social_account_ids)
    )
    platforms = dict(ctx.account_platforms)
    flags: dict[str, dict[str, Any]] = {}
    for account in accounts:
        key = str(account.id)
        platforms[key] = account.platform
        flags[key] = dict(account.capability_flags or {})
    return enrich_compile_context(
        ctx,
        platforms=platforms,
        flag_maps=flags,
        runtime=runtime,
    )
