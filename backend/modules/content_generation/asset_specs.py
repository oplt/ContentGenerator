from __future__ import annotations

from typing import Any, Protocol

from backend.modules.content_generation.asset_specs_media import (
    append_formatter_and_renderer_specs,
    build_media_platform_specs,
)
from backend.modules.content_generation.asset_specs_social import build_social_platform_specs
from backend.modules.content_generation.asset_specs_text import (
    build_evidence_lines,
    build_stage_and_report_specs,
    build_text_variant_specs,
)
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
    def _sentence_split(self, text: str) -> list[str]: ...


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
    evidence_lines = build_evidence_lines(brief=brief, source_articles=source_articles)
    platform_set = set(effective_platforms)

    manifest: list[dict[str, Any]] = []
    manifest.extend(
        build_stage_and_report_specs(
            svc,
            cluster=cluster,
            brief=brief,
            orch_result=orch_result,
            source_articles=source_articles,
            evidence_lines=evidence_lines,
            effective_platforms=effective_platforms,
        )
    )
    manifest.extend(
        build_text_variant_specs(
            cluster=cluster,
            orch_result=orch_result,
            effective_platforms=effective_platforms,
            primary_platform=primary_platform,
        )
    )
    manifest.extend(
        build_social_platform_specs(
            svc,
            cluster=cluster,
            brief=brief,
            plan=plan,
            orch_result=orch_result,
            platform_set=platform_set,
            hashtags=hashtags,
            safer_variant=safer_variant,
            thread_text=thread_text,
        )
    )
    manifest.extend(
        build_media_platform_specs(
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
    append_formatter_and_renderer_specs(
        svc,
        manifest=manifest,
        cluster=cluster,
        brief=brief,
        plan=plan,
        profile=profile,
        platform_set=platform_set,
    )
    return manifest
