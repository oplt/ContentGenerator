from __future__ import annotations

from typing import Any


def build_brand_voice_report(
    *,
    plan: Any,
    brief: Any,
    profile: Any,
    effective_tone: str,
    platforms: list[str],
    asset_manifest: list[dict[str, Any]],
) -> dict[str, object]:
    profile_platforms = getattr(profile, "preferred_platforms", []) if profile is not None else []
    if not isinstance(profile_platforms, list):
        profile_platforms = []
    plan_platforms = plan.target_platforms if isinstance(getattr(plan, "target_platforms", []), list) else []
    target_platforms = list(profile_platforms or plan_platforms)

    profile_tone = getattr(profile, "tone", None) if profile is not None else None
    brief_tone = getattr(brief, "tone_guidance", None)
    expected_tone = next(
        (
            value
            for value in (profile_tone, brief_tone, getattr(plan, "tone", None))
            if isinstance(value, str)
        ),
        plan.tone,
    )

    profile_cta = getattr(profile, "default_cta", None) if profile is not None else None
    brief_cta = getattr(brief, "cta_strategy", "")
    plan_cta = getattr(plan, "recommended_cta", None)
    expected_cta = next(
        (value for value in (profile_cta, plan_cta, brief_cta) if isinstance(value, str) and value),
        "",
    )
    sample_text = " ".join(
        str(asset.get("content", ""))
        for asset in asset_manifest[:4]
        if str(asset.get("content", "")).strip()
    ).lower()

    issues: list[str] = []
    if expected_tone and effective_tone != expected_tone:
        issues.append(f"Generation tone '{effective_tone}' differs from profile tone '{expected_tone}'")
    if target_platforms:
        missing = sorted(set(target_platforms) - set(platforms))
        if missing:
            issues.append(f"Missing preferred platforms: {', '.join(missing)}")
    if expected_cta and expected_cta.lower()[:24] not in sample_text:
        issues.append("Expected CTA is weakly represented across the package")
    return {
        "compliant": not issues,
        "expected_tone": expected_tone,
        "effective_tone": effective_tone,
        "preferred_platforms": target_platforms,
        "issues": issues,
    }


class BrandVoiceMixin:
    def _build_brand_voice_report(
        self,
        *,
        plan: Any,
        brief: Any,
        profile: Any,
        effective_tone: str,
        platforms: list[str],
        asset_manifest: list[dict[str, Any]],
    ) -> dict[str, object]:
        return build_brand_voice_report(
            plan=plan,
            brief=brief,
            profile=profile,
            effective_tone=effective_tone,
            platforms=platforms,
            asset_manifest=asset_manifest,
        )
