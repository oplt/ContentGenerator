"""Canonical editorial content helpers (Phase 11).

Artifact layers (do not collapse these):

* GenerateText — raw reusable AI operation (no ContentJob)
* ContentJob — durable editorial / canonical content
* ContentVariant — account/platform specialization (Phase 10)
* PublishingJob — distribution intent
"""

from __future__ import annotations

from typing import Any

from backend.modules.content_generation.models import GeneratedAsset, GeneratedAssetType


def extract_canonical_text(
    assets: list[GeneratedAsset] | list[Any],
    *,
    primary_platform: str | None = None,
) -> str | None:
    """Pick durable editorial body from generation assets (not platform variants).

    Preference:
    1. writer_stage (orchestrator draft before per-platform formatting)
    2. text_variant for primary_platform
    3. any text_variant with content
    """
    writer: str | None = None
    primary: str | None = None
    any_variant: str | None = None
    primary_key = (primary_platform or "").strip().lower() or None

    for asset in assets:
        asset_type = str(getattr(asset, "asset_type", "") or "")
        text = getattr(asset, "text_content", None)
        if not isinstance(text, str) or not text.strip():
            continue
        cleaned = text.strip()
        if asset_type == GeneratedAssetType.WRITER_STAGE.value:
            writer = cleaned
            continue
        if asset_type != GeneratedAssetType.TEXT_VARIANT.value:
            continue
        platform = str(getattr(asset, "platform", "") or "").strip().lower() or None
        if primary_key and platform == primary_key and primary is None:
            primary = cleaned
        if any_variant is None:
            any_variant = cleaned

    return writer or primary or any_variant


def canonical_primary_platform(job: Any) -> str | None:
    """Best-effort primary platform from job grounding / provider metadata."""
    grounding = getattr(job, "grounding_bundle", None)
    if isinstance(grounding, dict):
        trace = grounding.get("inference_trace")
        if isinstance(trace, dict) and trace.get("planner_platforms"):
            platforms = trace.get("planner_platforms")
            if isinstance(platforms, list) and platforms:
                return str(platforms[0])
        fps = grounding.get("variant_fingerprints")
        if isinstance(fps, dict) and fps:
            # fingerprint keys are "platform:digest"
            first = next(iter(fps.keys()))
            return str(first).split(":", 1)[0] or None
    meta = getattr(job, "provider_metadata", None)
    if isinstance(meta, dict) and meta.get("primary_platform"):
        return str(meta["primary_platform"])
    return None
