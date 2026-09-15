from __future__ import annotations

from typing import Any, Protocol

from backend.modules.content_generation.generation_context import PLATFORM_LIMITS
from backend.modules.content_generation.models import GeneratedAssetType
from backend.modules.story_intelligence.models import StoryCluster


class _SocialAssetSpecDeps(Protocol):
    def _trim(self, text: str, limit: int) -> str: ...
    def _serialize_payload(self, payload: object) -> str: ...
    def _sentence_split(self, text: str) -> list[str]: ...


def build_social_platform_specs(
    svc: _SocialAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    orch_result: Any,
    platform_set: set[str],
    hashtags: list[str],
    safer_variant: str,
    thread_text: str,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if "x" in platform_set:
        specs.extend(_build_x_specs(svc, orch_result=orch_result, hashtags=hashtags, safer_variant=safer_variant, thread_text=thread_text))
    if "threads" in platform_set:
        specs.extend(_build_threads_specs(cluster=cluster, orch_result=orch_result))
    if "bluesky" in platform_set:
        specs.extend(
            _build_bluesky_specs(svc, cluster=cluster, orch_result=orch_result, thread_text=thread_text)
        )
    if "instagram" in platform_set:
        specs.extend(
            _build_instagram_specs(
                svc,
                cluster=cluster,
                brief=brief,
                plan=plan,
                orch_result=orch_result,
                hashtags=hashtags,
            )
        )
    return specs


def _build_x_specs(
    svc: _SocialAssetSpecDeps,
    *,
    orch_result: Any,
    hashtags: list[str],
    safer_variant: str,
    thread_text: str,
) -> list[dict[str, Any]]:
    return [
        {
            "asset_type": GeneratedAssetType.HOOK,
            "platform": "x",
            "variant_label": "hook_variants",
            "content": svc._serialize_payload(orch_result.optimizer.variants[:3] or [orch_result.planner.hook]),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": "x"},
        },
        {
            "asset_type": GeneratedAssetType.THREAD,
            "platform": "x",
            "variant_label": "thread",
            "content": thread_text,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "x"},
        },
        {
            "asset_type": GeneratedAssetType.TEXT_VARIANT,
            "platform": "x",
            "variant_label": "safe",
            "content": safer_variant,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "x", "risk_profile": "safer"},
        },
        {
            "asset_type": GeneratedAssetType.HASHTAG_PACK,
            "platform": "x",
            "variant_label": "keywords",
            "content": " ".join(hashtags[:8]),
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "x"},
        },
    ]


def _build_threads_specs(*, cluster: StoryCluster, orch_result: Any) -> list[dict[str, Any]]:
    base = orch_result.writer.drafts.get("threads") or orch_result.final_draft or cluster.summary or cluster.headline
    return [
        {
            "asset_type": GeneratedAssetType.TEXT_VARIANT,
            "platform": "threads",
            "variant_label": "conversational",
            "content": f"{base}\n\nWhat stands out most to you here?",
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "threads"},
        },
        {
            "asset_type": GeneratedAssetType.TEXT_VARIANT,
            "platform": "threads",
            "variant_label": "reply_bait",
            "content": f"{base}\n\nDrop your take below.",
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "threads"},
        },
        {
            "asset_type": GeneratedAssetType.CAPTION,
            "platform": "threads",
            "variant_label": "media_caption",
            "content": f"{cluster.headline}\n{cluster.summary or ''}".strip(),
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "threads"},
        },
    ]


def _build_bluesky_specs(
    svc: _SocialAssetSpecDeps,
    *,
    cluster: StoryCluster,
    orch_result: Any,
    thread_text: str,
) -> list[dict[str, Any]]:
    concise = svc._trim(
        orch_result.writer.drafts.get("bluesky") or orch_result.final_draft or cluster.headline,
        PLATFORM_LIMITS["bluesky"],
    )
    return [
        {
            "asset_type": GeneratedAssetType.TEXT_VARIANT,
            "platform": "bluesky",
            "variant_label": "concise",
            "content": concise,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "bluesky"},
        },
        {
            "asset_type": GeneratedAssetType.THREAD,
            "platform": "bluesky",
            "variant_label": "starter",
            "content": svc._trim(thread_text, PLATFORM_LIMITS["bluesky"]),
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "bluesky"},
        },
        {
            "asset_type": GeneratedAssetType.IMAGE_CAPTION,
            "platform": "bluesky",
            "variant_label": "image_caption",
            "content": cluster.summary or cluster.headline,
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "bluesky"},
        },
    ]


def _build_instagram_specs(
    svc: _SocialAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    orch_result: Any,
    hashtags: list[str],
) -> list[dict[str, Any]]:
    carousel_slides = [
        orch_result.planner.hook or cluster.headline,
        *(
            list(getattr(brief, "talking_points", []) or [])[:3]
            or svc._sentence_split(cluster.summary or cluster.headline)[:3]
        ),
        plan.recommended_cta or getattr(brief, "cta_strategy", "") or "Follow for more",
    ]
    return [
        {
            "asset_type": GeneratedAssetType.CAPTION,
            "platform": "instagram",
            "variant_label": "reel_caption",
            "content": f"{cluster.headline}\n\n{cluster.summary or ''}\n\n{plan.recommended_cta or ''}".strip(),
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "instagram"},
        },
        {
            "asset_type": GeneratedAssetType.CAROUSEL_SLIDES,
            "platform": "instagram",
            "variant_label": "slides",
            "content": svc._serialize_payload(carousel_slides),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": "instagram"},
        },
        {
            "asset_type": GeneratedAssetType.CAPTION,
            "platform": "instagram",
            "variant_label": "post_caption",
            "content": orch_result.writer.drafts.get("instagram")
            or orch_result.final_draft
            or cluster.summary
            or cluster.headline,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "instagram"},
        },
        {
            "asset_type": GeneratedAssetType.HASHTAG_PACK,
            "platform": "instagram",
            "variant_label": "hashtags",
            "content": " ".join(hashtags[:12]),
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "instagram"},
        },
        {
            "asset_type": GeneratedAssetType.COVER_COPY,
            "platform": "instagram",
            "variant_label": "cover",
            "content": orch_result.planner.hook or cluster.headline,
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "instagram"},
        },
    ]
