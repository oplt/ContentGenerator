"""Sanitized snapshot fragments for ConfigResolver."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from backend.modules.content_strategy.models import Brand, BrandProfile, BrandSocialAccount
from backend.modules.publishing.account_selection import variant_fingerprint
from backend.modules.publishing.models import SocialAccount
from backend.modules.publishing.platform_capabilities import flags_to_capabilities
from backend.modules.workflows.config_merge import as_mapping, strip_secrets
from backend.modules.workflows.models import Automation, AutomationTarget


def _typed_caps_dump(account: SocialAccount) -> dict[str, Any]:
    return flags_to_capabilities(
        account.capability_flags, platform=account.platform
    ).model_dump(mode="json")


def brand_snapshot(brand: Brand | None) -> dict[str, Any] | None:
    if brand is None:
        return None
    return cast(
        dict[str, Any],
        strip_secrets(
            {
                "id": str(brand.id),
                "name": brand.name,
                "niche": brand.niche,
                "style_guide": as_mapping(brand.style_guide),
                "allowed_topics": list(brand.allowed_topics or []),
                "blocked_topics": list(brand.blocked_topics or []),
                "target_platforms": list(brand.target_platforms or []),
                "risk_policy": as_mapping(brand.risk_policy),
                "posting_policy": as_mapping(brand.posting_policy),
            }
        ),
    )


def profile_snapshot(profile: BrandProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return cast(
        dict[str, Any],
        strip_secrets(
            {
                "id": str(profile.id),
                "brand_id": str(profile.brand_id) if profile.brand_id else None,
                "name": profile.name,
                "niche": profile.niche,
                "tone": profile.tone,
                "audience": profile.audience,
                "voice_notes": profile.voice_notes,
                "preferred_platforms": list(profile.preferred_platforms or []),
                "default_cta": profile.default_cta,
                "hashtags_strategy": profile.hashtags_strategy,
                "risk_tolerance": profile.risk_tolerance,
                "require_whatsapp_approval": profile.require_whatsapp_approval,
                "guardrails": as_mapping(profile.guardrails),
                "visual_style": as_mapping(profile.visual_style),
            }
        ),
    )


def automation_snapshot(automation: Automation | None) -> dict[str, Any] | None:
    if automation is None:
        return None
    settings = as_mapping(automation.settings)
    return cast(
        dict[str, Any],
        strip_secrets(
            {
                "id": str(automation.id),
                "name": automation.name,
                "brand_id": str(automation.brand_id),
                "workflow_version_id": str(automation.workflow_version_id),
                "timezone": automation.timezone,
                "settings": {
                    "config": as_mapping(settings.get("config")),
                    "editorial": as_mapping(settings.get("editorial")),
                    "node_overrides": as_mapping(settings.get("node_overrides")),
                },
            }
        ),
    )


def accounts_snapshot(
    accounts: list[SocialAccount],
    bsa_by_account: dict[UUID, BrandSocialAccount],
    targets: list[AutomationTarget],
) -> list[dict[str, Any]]:
    target_by_account = {t.social_account_id: t for t in targets}
    rows: list[dict[str, Any]] = []
    for account in accounts:
        bsa = bsa_by_account.get(account.id)
        target = target_by_account.get(account.id)
        rows.append(
            cast(
                dict[str, Any],
                strip_secrets(
                    {
                        "social_account_id": str(account.id),
                        "platform": account.platform,
                        "handle": account.handle,
                        "display_name": account.display_name,
                        "capability_flags": as_mapping(account.capability_flags),
                        "platform_capabilities": _typed_caps_dump(account),
                        "variant_fingerprint": variant_fingerprint(account),
                        "default_content_format": bsa.default_content_format if bsa else None,
                        "generation_overrides": as_mapping(
                            bsa.generation_overrides if bsa else None
                        ),
                        "target_overrides": as_mapping(
                            target.overrides_json if target else None
                        ),
                    }
                ),
            )
        )
    return rows
