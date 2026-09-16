"""Load and sanitize config layers for ConfigResolver."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_strategy.models import Brand, BrandProfile, BrandSocialAccount
from backend.modules.publishing.models import SocialAccount
from backend.modules.publishing.repository import PublishingRepository
from backend.modules.workflows.config_merge import as_mapping, deep_merge, strip_secrets
from backend.modules.workflows.graph_schema import CompileContext
from backend.modules.workflows.models import Automation, AutomationTarget


async def load_automation(
    db: AsyncSession, tenant_id: UUID, automation_id: UUID | None
) -> Automation | None:
    if automation_id is None:
        return None
    result = await db.execute(
        select(Automation).where(
            Automation.tenant_id == tenant_id,
            Automation.id == automation_id,
            Automation.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def load_brand(db: AsyncSession, tenant_id: UUID, brand_id: UUID | None) -> Brand | None:
    if brand_id is None:
        return None
    result = await db.execute(
        select(Brand).where(
            Brand.tenant_id == tenant_id,
            Brand.id == brand_id,
            Brand.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def load_profile(
    db: AsyncSession, tenant_id: UUID, brand_id: UUID | None
) -> BrandProfile | None:
    if brand_id is None:
        return None
    result = await db.execute(
        select(BrandProfile)
        .where(
            BrandProfile.tenant_id == tenant_id,
            BrandProfile.brand_id == brand_id,
            BrandProfile.deleted_at.is_(None),
        )
        .order_by(BrandProfile.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def load_targets_and_accounts(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    automation: Automation | None,
    brand_id: UUID | None,
    compile_context: CompileContext | None,
) -> tuple[list[AutomationTarget], list[SocialAccount], dict[UUID, BrandSocialAccount]]:
    targets: list[AutomationTarget] = []
    account_ids: list[UUID] = []
    if automation is not None:
        result = await db.execute(
            select(AutomationTarget).where(
                AutomationTarget.tenant_id == tenant_id,
                AutomationTarget.automation_id == automation.id,
                AutomationTarget.enabled.is_(True),
                AutomationTarget.deleted_at.is_(None),
            )
        )
        targets = list(result.scalars().all())
        account_ids = [t.social_account_id for t in targets]
    if not account_ids and compile_context is not None:
        account_ids = list(compile_context.social_account_ids)

    accounts: list[SocialAccount] = []
    if account_ids:
        accounts = await PublishingRepository(db).get_social_accounts_by_ids(
            tenant_id, account_ids
        )
        accounts.sort(key=lambda a: str(a.id))

    bsa_by_account: dict[UUID, BrandSocialAccount] = {}
    if brand_id is not None and account_ids:
        result = await db.execute(
            select(BrandSocialAccount).where(
                BrandSocialAccount.tenant_id == tenant_id,
                BrandSocialAccount.brand_id == brand_id,
                BrandSocialAccount.social_account_id.in_(account_ids),
                BrandSocialAccount.deleted_at.is_(None),
                BrandSocialAccount.enabled.is_(True),
            )
        )
        for row in result.scalars().all():
            bsa = cast(BrandSocialAccount, row)
            bsa_by_account[bsa.social_account_id] = bsa
    return targets, accounts, bsa_by_account


def brand_layer(brand: Brand | None, profile: BrandProfile | None) -> dict[str, Any]:
    layer: dict[str, Any] = {}
    if brand is not None:
        layer = deep_merge(
            layer,
            as_mapping(brand.style_guide),
            {
                "niche": brand.niche,
                "allowed_topics": list(brand.allowed_topics or []),
                "blocked_topics": list(brand.blocked_topics or []),
                "target_platforms": list(brand.target_platforms or []),
            },
            as_mapping(brand.risk_policy),
            as_mapping(brand.posting_policy),
        )
    if profile is not None:
        layer = deep_merge(
            layer,
            {
                "tone": profile.tone,
                "audience": profile.audience,
                "voice_notes": profile.voice_notes,
                "niche": profile.niche,
                "default_cta": profile.default_cta,
                "hashtags_strategy": profile.hashtags_strategy,
                "risk_tolerance": profile.risk_tolerance,
                "preferred_platforms": list(profile.preferred_platforms or []),
            },
            as_mapping(profile.guardrails),
            as_mapping(profile.visual_style),
        )
    return cast(dict[str, Any], strip_secrets(layer))


def automation_layers(
    automation: Automation | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if automation is None:
        return {}, {}
    settings = as_mapping(automation.settings)
    global_layer = deep_merge(
        as_mapping(settings.get("config")),
        as_mapping(settings.get("editorial")),
    )
    return (
        cast(dict[str, Any], strip_secrets(global_layer)),
        cast(dict[str, Any], strip_secrets(as_mapping(settings.get("node_overrides")))),
    )


def account_layers(
    targets: list[AutomationTarget],
    accounts: list[SocialAccount],
    bsa_by_account: dict[UUID, BrandSocialAccount],
) -> tuple[dict[str, Any], dict[str, Any]]:
    layer: dict[str, Any] = {}
    node_overrides: dict[str, Any] = {}
    target_by_account = {t.social_account_id: t for t in targets}
    for account in accounts:
        target = target_by_account.get(account.id)
        bsa = bsa_by_account.get(account.id)
        account_bits = deep_merge(
            as_mapping(target.overrides_json if target else None),
            as_mapping(bsa.generation_overrides if bsa else None),
            as_mapping(bsa.publishing_policy if bsa else None),
            as_mapping(bsa.platform_policy if bsa else None),
            (
                {"default_content_format": bsa.default_content_format}
                if bsa and bsa.default_content_format
                else {}
            ),
        )
        per_node = as_mapping(account_bits.pop("node_overrides", None))
        layer = deep_merge(layer, account_bits)
        for node_id, overrides in per_node.items():
            node_overrides[node_id] = deep_merge(
                as_mapping(node_overrides.get(node_id)),
                as_mapping(overrides),
            )
    return (
        cast(dict[str, Any], strip_secrets(layer)),
        cast(dict[str, Any], strip_secrets(node_overrides)),
    )


def run_layer(
    initial_inputs: dict[str, Any],
    trigger_payload: dict[str, Any],
    run_config: dict[str, Any],
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        strip_secrets(
            deep_merge(
                as_mapping(initial_inputs.get("config")),
                as_mapping(trigger_payload.get("config")),
                run_config,
            )
        ),
    )
