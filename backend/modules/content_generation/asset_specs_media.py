from __future__ import annotations

from typing import Any, Protocol

from backend.modules.content_generation.generation_context import PLATFORM_LIMITS
from backend.modules.content_generation.models import GeneratedAssetType
from backend.modules.story_intelligence.models import StoryCluster


class _MediaAssetSpecDeps(Protocol):
    def _trim(self, text: str, limit: int) -> str: ...
    def _build_thread(self, headline: str, summary: str, talking_points: list[str], cta: str) -> str: ...
    def _build_renderer_input_payload(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _serialize_payload(self, payload: object) -> str: ...
    def _sentence_split(self, text: str) -> list[str]: ...


def build_media_platform_specs(
    svc: _MediaAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    orch_result: Any,
    platform_set: set[str],
    hashtags: list[str],
    evidence_lines: list[str],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if "tiktok" in platform_set:
        specs.extend(_build_tiktok_specs(svc, cluster=cluster, brief=brief, plan=plan, orch_result=orch_result))
    if "youtube" in platform_set or "youtube_shorts" in platform_set:
        specs.extend(
            _build_youtube_specs(
                svc,
                cluster=cluster,
                brief=brief,
                plan=plan,
                orch_result=orch_result,
                platform_set=platform_set,
                hashtags=hashtags,
                evidence_lines=evidence_lines,
            )
        )
    return specs


def append_formatter_and_renderer_specs(
    svc: _MediaAssetSpecDeps,
    *,
    manifest: list[dict[str, Any]],
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    profile: Any,
    platform_set: set[str],
) -> None:
    formatter_manifest = [
        {
            "asset_type": str(item["asset_type"].value),
            "platform": item["platform"],
            "variant_label": item["variant_label"],
            "mime_type": item["mime_type"],
        }
        for item in manifest
    ]
    manifest.append(
        {
            "asset_type": GeneratedAssetType.FORMATTER_STAGE,
            "platform": None,
            "variant_label": "formatter",
            "content": svc._serialize_payload(formatter_manifest),
            "mime_type": "application/json",
            "asset_metadata": {"stage": "formatter"},
        }
    )
    for platform in sorted(platform_set.intersection({"instagram", "tiktok", "youtube", "youtube_shorts"})):
        renderer_payload = svc._build_renderer_input_payload(
            platform=platform,
            headline=cluster.headline,
            summary=cluster.summary or "",
            script=svc._build_thread(
                cluster.headline,
                cluster.summary or "",
                list(getattr(brief, "talking_points", []) or []),
                plan.recommended_cta or "",
            ),
            cta=plan.recommended_cta or "",
            talking_points=list(getattr(brief, "talking_points", []) or []),
            profile=profile,
        )
        manifest.append(
            {
                "asset_type": GeneratedAssetType.RENDERER_INPUT,
                "platform": platform,
                "variant_label": "renderer_input",
                "content": svc._serialize_payload(renderer_payload),
                "mime_type": "application/json",
                "asset_metadata": {"stage": "renderer_input"},
            }
        )


def _build_tiktok_specs(
    svc: _MediaAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    orch_result: Any,
) -> list[dict[str, Any]]:
    script = svc._build_thread(
        cluster.headline,
        cluster.summary or "",
        list(getattr(brief, "talking_points", []) or []),
        plan.recommended_cta or "",
    )
    subtitle_plan = svc._sentence_split(script)
    return [
        {
            "asset_type": GeneratedAssetType.HOOK,
            "platform": "tiktok",
            "variant_label": "hook",
            "content": orch_result.planner.hook or cluster.headline,
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "tiktok"},
        },
        {
            "asset_type": GeneratedAssetType.SCRIPT,
            "platform": "tiktok",
            "variant_label": "short_script",
            "content": script,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "tiktok"},
        },
        {
            "asset_type": GeneratedAssetType.CAPTION,
            "platform": "tiktok",
            "variant_label": "caption",
            "content": orch_result.writer.drafts.get("tiktok")
            or orch_result.final_draft
            or cluster.summary
            or cluster.headline,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": "tiktok"},
        },
        {
            "asset_type": GeneratedAssetType.ONSCREEN_TEXT,
            "platform": "tiktok",
            "variant_label": "onscreen_plan",
            "content": svc._serialize_payload(subtitle_plan[:6]),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": "tiktok"},
        },
        {
            "asset_type": GeneratedAssetType.SHOT_LIST,
            "platform": "tiktok",
            "variant_label": "shot_list",
            "content": svc._serialize_payload((getattr(brief, "talking_points", []) or subtitle_plan)[:6]),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": "tiktok"},
        },
        {
            "asset_type": GeneratedAssetType.SUBTITLE,
            "platform": "tiktok",
            "variant_label": "subtitles",
            "content": "\n".join(subtitle_plan),
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": "tiktok"},
        },
    ]


def _build_youtube_specs(
    svc: _MediaAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    orch_result: Any,
    platform_set: set[str],
    hashtags: list[str],
    evidence_lines: list[str],
) -> list[dict[str, Any]]:
    youtube_platform = "youtube_shorts" if "youtube_shorts" in platform_set else "youtube"
    script = svc._build_thread(
        cluster.headline,
        cluster.summary or "",
        list(getattr(brief, "talking_points", []) or []),
        plan.recommended_cta or "",
    )
    title_variants = [
        svc._trim(orch_result.planner.hook or cluster.headline, PLATFORM_LIMITS["youtube_title"]),
        svc._trim(f"{cluster.primary_topic.title()}: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
        svc._trim(f"What changed: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
    ]
    return [
        {
            "asset_type": GeneratedAssetType.HOOK,
            "platform": youtube_platform,
            "variant_label": "hook",
            "content": orch_result.planner.hook or cluster.headline,
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.SCRIPT,
            "platform": youtube_platform,
            "variant_label": "short_script",
            "content": script,
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.TITLE_VARIANTS,
            "platform": youtube_platform,
            "variant_label": "titles",
            "content": svc._serialize_payload(title_variants),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.DESCRIPTION,
            "platform": youtube_platform,
            "variant_label": "description",
            "content": svc._trim(
                f"{cluster.summary or cluster.headline}\n\n{plan.recommended_cta or ''}\n\nSources:\n"
                + "\n".join(evidence_lines[:3]),
                PLATFORM_LIMITS["youtube_description"],
            ),
            "mime_type": "text/markdown",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.TAGS,
            "platform": youtube_platform,
            "variant_label": "tags",
            "content": ", ".join([tag.lstrip("#") for tag in hashtags[:12]]),
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.BEAT_SHEET,
            "platform": youtube_platform,
            "variant_label": "beats",
            "content": svc._serialize_payload(svc._sentence_split(script)[:6]),
            "mime_type": "application/json",
            "asset_metadata": {"platform_package": youtube_platform},
        },
        {
            "asset_type": GeneratedAssetType.COVER_COPY,
            "platform": youtube_platform,
            "variant_label": "thumbnail_text",
            "content": title_variants[0],
            "mime_type": "text/plain",
            "asset_metadata": {"platform_package": youtube_platform},
        },
    ]
