from __future__ import annotations

from typing import Any, Protocol

from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster


class _AssetSpecDeps(Protocol):
    def _trim(self, text: str, limit: int) -> str: ...
    def _build_hashtags(self, topic: str, strategy: str) -> str: ...
    def _build_thread(self, headline: str, summary: str, talking_points: list[str], cta: str) -> str: ...
    def _build_renderer_input_payload(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _serialize_payload(self, payload: object) -> str: ...
    def _build_attribution_list(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _build_policy_flags(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _build_brand_voice_report(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _measure_originality(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _build_fact_checklist(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...


def build_platform_asset_specs(
    svc: _AssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    profile: Any,
    orch_result: Any,
    effective_platforms: list[str],
    primary_platform: str,
    source_articles: list[NormalizedArticle],
) -> list[dict[str, Any]]:
    hashtags = orch_result.writer.hashtags or svc._build_hashtags(cluster.primary_topic, plan.hashtags_strategy).split()
    safer_variant = orch_result.reviewer.revised_draft or f"{cluster.headline}. {cluster.summary}".strip()
    thread_text = svc._build_thread(
        cluster.headline,
        cluster.summary or "",
        list(getattr(brief, "talking_points", []) or orch_result.planner.structure or []),
        plan.recommended_cta or "",
    )
    evidence_lines = [
        f"- {article.source_name}: {article.title} ({article.canonical_url})"
        for article in source_articles[:5]
    ] or [f"- {url}" for url in getattr(brief, "evidence_links", [])[:5]]
    fact_checklist = svc._build_fact_checklist(
        cluster=cluster,
        source_articles=source_articles,
        claims=list(orch_result.extractor.claims or []),
        evidence_links=list(getattr(brief, "evidence_links", []) or []),
    )
    attribution_list = svc._build_attribution_list(brief=brief, source_articles=source_articles)
    policy_flags = svc._build_policy_flags(
        cluster=cluster,
        brief=brief,
        orch_result=orch_result,
        fact_checklist=fact_checklist,
        source_articles=source_articles,
        effective_platforms=effective_platforms,
    )

    manifest: list[dict[str, Any]] = [
        {
            "asset_type": GeneratedAssetType.PLANNER_STAGE,
            "platform": None,
            "variant_label": "planner",
            "content": svc._serialize_payload(orch_result.planner.model_dump()),
            "mime_type": "application/json",
            "asset_metadata": {"stage": "planner"},
        },
        {
            "asset_type": GeneratedAssetType.WRITER_STAGE,
            "platform": None,
            "variant_label": "writer",
            "content": svc._serialize_payload(orch_result.writer.model_dump()),
            "mime_type": "application/json",
            "asset_metadata": {"stage": "writer"},
        },
        {
            "asset_type": GeneratedAssetType.REVIEWER_STAGE,
            "platform": None,
            "variant_label": "reviewer",
            "content": svc._serialize_payload(orch_result.reviewer.model_dump()),
            "mime_type": "application/json",
            "asset_metadata": {"stage": "reviewer"},
        },
        {
            "asset_type": GeneratedAssetType.RESEARCH_DIGEST,
            "platform": None,
            "variant_label": "evidence",
            "content": "\n".join(evidence_lines),
            "mime_type": "text/markdown",
            "asset_metadata": {"source_count": str(len(source_articles))},
        },
        {
            "asset_type": GeneratedAssetType.FACT_CHECKLIST,
            "platform": None,
            "variant_label": "facts",
            "content": svc._serialize_payload(fact_checklist),
            "mime_type": "application/json",
            "asset_metadata": {"report": "fact_checklist"},
        },
        {
            "asset_type": GeneratedAssetType.ATTRIBUTION_LIST,
            "platform": None,
            "variant_label": "attribution",
            "content": svc._serialize_payload(attribution_list),
            "mime_type": "application/json",
            "asset_metadata": {"report": "attribution"},
        },
        {
            "asset_type": GeneratedAssetType.POLICY_FLAGS,
            "platform": None,
            "variant_label": "policy",
            "content": svc._serialize_payload(policy_flags),
            "mime_type": "application/json",
            "asset_metadata": {"report": "policy_flags"},
        },
    ]

    for platform in effective_platforms:
        draft_text = orch_result.writer.drafts.get(platform) or orch_result.final_draft or cluster.headline
        manifest.append(
            {
                "asset_type": GeneratedAssetType.TEXT_VARIANT,
                "platform": platform,
                "variant_label": "A",
                "content": draft_text,
                "mime_type": "text/markdown",
                "asset_metadata": {"role": "writer_primary"},
            }
        )

    for index, variant_text in enumerate(orch_result.optimizer.variants[1:], start=1):
        manifest.append(
            {
                "asset_type": GeneratedAssetType.TEXT_VARIANT,
                "platform": primary_platform,
                "variant_label": chr(ord("A") + index),
                "content": variant_text,
                "mime_type": "text/markdown",
                "asset_metadata": {"role": "optimizer_variant", "variant_index": str(index)},
            }
        )

    platform_set = set(effective_platforms)
    if "x" in platform_set:
        manifest.extend(
            [
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
        )
    if "threads" in platform_set:
        base = orch_result.writer.drafts.get("threads") or orch_result.final_draft or cluster.summary or cluster.headline
        manifest.extend(
            [
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
        )
    if "bluesky" in platform_set:
        concise = svc._trim(orch_result.writer.drafts.get("bluesky") or orch_result.final_draft or cluster.headline, PLATFORM_LIMITS["bluesky"])
        manifest.extend(
            [
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
        )
    if "instagram" in platform_set:
        carousel_slides = [
            orch_result.planner.hook or cluster.headline,
            *(list(getattr(brief, "talking_points", []) or [])[:3] or svc._sentence_split(cluster.summary or cluster.headline)[:3]),
            plan.recommended_cta or getattr(brief, "cta_strategy", "") or "Follow for more",
        ]
        manifest.extend(
            [
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
                    "content": orch_result.writer.drafts.get("instagram") or orch_result.final_draft or cluster.summary or cluster.headline,
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
        )
    if "tiktok" in platform_set:
        script = svc._build_thread(cluster.headline, cluster.summary or "", list(getattr(brief, "talking_points", []) or []), plan.recommended_cta or "")
        subtitle_plan = svc._sentence_split(script)
        manifest.extend(
            [
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
                    "content": orch_result.writer.drafts.get("tiktok") or orch_result.final_draft or cluster.summary or cluster.headline,
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
        )
    if "youtube" in platform_set or "youtube_shorts" in platform_set:
        youtube_platform = "youtube_shorts" if "youtube_shorts" in platform_set else "youtube"
        script = svc._build_thread(cluster.headline, cluster.summary or "", list(getattr(brief, "talking_points", []) or []), plan.recommended_cta or "")
        title_variants = [
            svc._trim(orch_result.planner.hook or cluster.headline, PLATFORM_LIMITS["youtube_title"]),
            svc._trim(f"{cluster.primary_topic.title()}: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
            svc._trim(f"What changed: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
        ]
        manifest.extend(
            [
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
                        f"{cluster.summary or cluster.headline}\n\n{plan.recommended_cta or ''}\n\nSources:\n" + "\n".join(evidence_lines[:3]),
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
        )

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

    return manifest

