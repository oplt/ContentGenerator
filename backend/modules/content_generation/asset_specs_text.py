from __future__ import annotations

from typing import Any, Protocol

from backend.modules.content_generation.models import GeneratedAssetType
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster


class _TextAssetSpecDeps(Protocol):
    def _serialize_payload(self, payload: object) -> str: ...
    def _build_fact_checklist(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _build_attribution_list(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...
    def _build_policy_flags(self, *args: Any, **kwargs: Any) -> dict[str, object]: ...


def build_evidence_lines(
    *,
    brief: Any,
    source_articles: list[NormalizedArticle],
) -> list[str]:
    return [
        f"- {article.source_name}: {article.title} ({article.canonical_url})"
        for article in source_articles[:5]
    ] or [f"- {url}" for url in getattr(brief, "evidence_links", [])[:5]]


def build_stage_and_report_specs(
    svc: _TextAssetSpecDeps,
    *,
    cluster: StoryCluster,
    brief: Any,
    orch_result: Any,
    source_articles: list[NormalizedArticle],
    evidence_lines: list[str],
    effective_platforms: list[str],
) -> list[dict[str, Any]]:
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
    return [
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


def build_text_variant_specs(
    *,
    cluster: StoryCluster,
    orch_result: Any,
    effective_platforms: list[str],
    primary_platform: str,
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for platform in effective_platforms:
        draft_text = orch_result.writer.drafts.get(platform) or orch_result.final_draft or cluster.headline
        specs.append(
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
        specs.append(
            {
                "asset_type": GeneratedAssetType.TEXT_VARIANT,
                "platform": primary_platform,
                "variant_label": chr(ord("A") + index),
                "content": variant_text,
                "mime_type": "text/markdown",
                "asset_metadata": {"role": "optimizer_variant", "variant_index": str(index)},
            }
        )
    return specs
