from __future__ import annotations

import json
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.content_generation.brand_voice import build_brand_voice_report
from backend.modules.content_generation.models import (
    ContentJob,
    GeneratedAsset,
    GeneratedAssetGroup,
    GeneratedAssetType,
)
from backend.modules.content_generation.originality import measure_originality
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster


class _AssetPersistSvc(Protocol):
    db: AsyncSession

    def _build_platform_asset_specs(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...

    async def _create_assets_batch(self, specs: list[dict[str, Any]]) -> list[GeneratedAsset]: ...


def serialize_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


class AssetPersistenceMixin:
    db: AsyncSession

    def _serialize_payload(self, payload: object) -> str:
        return serialize_payload(payload)

    async def _create_asset(
        self,
        *,
        tenant_id: UUID,
        asset_group_id: UUID | None,
        content_job_id: UUID,
        asset_type: str,
        platform: str | None,
        variant_label: str | None,
        text_content: str,
        source_trace: dict[str, str],
        mime_type: str = "text/markdown",
        asset_metadata: dict[str, str] | None = None,
    ) -> GeneratedAsset:
        assets = await self._create_assets_batch(
            [
                {
                    "tenant_id": tenant_id,
                    "asset_group_id": asset_group_id,
                    "content_job_id": content_job_id,
                    "asset_type": asset_type,
                    "platform": platform,
                    "variant_label": variant_label,
                    "text_content": text_content,
                    "source_trace": source_trace,
                    "mime_type": mime_type,
                    "asset_metadata": asset_metadata or {"template_version": "v1"},
                }
            ]
        )
        return assets[0]

    async def _create_assets_batch(self, specs: list[dict[str, Any]]) -> list[GeneratedAsset]:
        """Build all assets then flush once (Phase 3.3)."""
        assets = [
            GeneratedAsset(
                tenant_id=spec["tenant_id"],
                asset_group_id=spec["asset_group_id"],
                content_job_id=spec["content_job_id"],
                asset_type=spec["asset_type"],
                platform=spec["platform"],
                variant_label=spec["variant_label"],
                mime_type=spec.get("mime_type", "text/markdown"),
                text_content=spec["text_content"],
                asset_metadata=spec.get("asset_metadata") or {"template_version": "v1"},
                source_trace=spec["source_trace"],
            )
            for spec in specs
        ]
        if assets:
            self.db.add_all(assets)
            await self.db.flush()
        return assets


async def persist_orchestrated_assets(
    svc: _AssetPersistSvc,
    *,
    tenant_id: UUID,
    job: ContentJob,
    asset_group: GeneratedAssetGroup,
    cluster: StoryCluster,
    brief: Any,
    plan: Any,
    profile: Any,
    orch_result: Any,
    preferred_platforms: list[str],
    source_articles: list[NormalizedArticle],
    effective_tone: str,
) -> tuple[list[dict[str, Any]], dict[str, object], dict[str, object], dict[str, object], str, list[str]]:
    """Build manifest, quality reports, and batch-insert text assets (pre media workers)."""
    source_trace = {
        "story_cluster_id": str(cluster.id),
        "headline": cluster.headline,
        "keywords": cluster.explainability.get("keywords", ""),
        "source_article_count": str(len(source_articles)),
        "orchestrator_scorer_composite": str(orch_result.scorer.composite),
        "orchestrator_reviewer_passed": str(orch_result.reviewer.passed),
        "orchestrator_extractor_vertical": orch_result.extractor.content_vertical,
    }

    planner_platforms = list(orch_result.planner.target_platforms or [])
    if preferred_platforms:
        effective_platforms = [p for p in preferred_platforms if p in set(planner_platforms)] or list(
            preferred_platforms
        )
    else:
        effective_platforms = planner_platforms or list(plan.target_platforms or [])
    primary_platform = effective_platforms[0] if effective_platforms else "x"
    asset_manifest = svc._build_platform_asset_specs(
        cluster=cluster,
        brief=brief,
        plan=plan,
        profile=profile,
        orch_result=orch_result,
        effective_platforms=effective_platforms,
        primary_platform=primary_platform,
        source_articles=source_articles,
    )
    originality_report = measure_originality(
        asset_manifest=asset_manifest,
        source_articles=source_articles,
    )
    brand_voice_report = build_brand_voice_report(
        plan=plan,
        brief=brief,
        profile=profile,
        effective_tone=effective_tone,
        platforms=effective_platforms,
        asset_manifest=asset_manifest,
    )
    asset_manifest.extend(
        [
            {
                "asset_type": GeneratedAssetType.BRAND_VOICE_REPORT,
                "platform": None,
                "variant_label": "brand_voice",
                "content": serialize_payload(brand_voice_report),
                "mime_type": "application/json",
                "asset_metadata": {"report": "brand_voice"},
            },
            {
                "asset_type": GeneratedAssetType.ORIGINALITY_REPORT,
                "platform": None,
                "variant_label": "originality",
                "content": serialize_payload(originality_report),
                "mime_type": "application/json",
                "asset_metadata": {"report": "originality"},
            },
        ]
    )
    asset_specs_for_insert: list[dict[str, Any]] = []
    for asset_spec in asset_manifest:
        asset_type_value = asset_spec["asset_type"]
        asset_type = (
            asset_type_value.value
            if isinstance(asset_type_value, GeneratedAssetType)
            else str(asset_type_value)
        )
        asset_specs_for_insert.append(
            {
                "tenant_id": tenant_id,
                "asset_group_id": asset_group.id,
                "content_job_id": job.id,
                "asset_type": asset_type,
                "platform": cast(str | None, asset_spec["platform"]),
                "variant_label": cast(str | None, asset_spec["variant_label"]),
                "text_content": str(asset_spec["content"]),
                "source_trace": source_trace,
                "mime_type": str(asset_spec["mime_type"]),
                "asset_metadata": cast(dict[str, str] | None, asset_spec.get("asset_metadata")),
            }
        )
    await svc._create_assets_batch(asset_specs_for_insert)

    policy_flags_raw = next(
        (
            str(item["content"])
            for item in asset_manifest
            if item["asset_type"] == GeneratedAssetType.POLICY_FLAGS
        ),
        "{}",
    )
    policy_payload = json.loads(policy_flags_raw)

    job.grounding_bundle = {
        **job.grounding_bundle,
        "risk_review": policy_payload,
        "risk_label": str(policy_payload.get("label", "low")),
        "inference_trace": {
            "scorer_composite": orch_result.scorer.composite,
            "scorer_reasoning": orch_result.scorer.reasoning,
            "reviewer_passed": orch_result.reviewer.passed,
            "reviewer_issues": orch_result.reviewer.issues,
            "optimizer_recommended_index": orch_result.optimizer.recommended_variant_index,
            "extractor_vertical": orch_result.extractor.content_vertical,
            "extractor_risk_flags": orch_result.extractor.risk_flags,
            "planner_format": orch_result.planner.recommended_format,
            "planner_platforms": orch_result.planner.target_platforms,
        },
    }
    asset_group.asset_types = sorted({item["asset_type"].value for item in asset_manifest})
    existing_generation_trace = (
        asset_group.generation_trace if isinstance(getattr(asset_group, "generation_trace", None), dict) else {}
    )
    asset_group.generation_trace = {
        **existing_generation_trace,
        "planner_platforms": effective_platforms,
        "primary_platform": primary_platform,
        "reviewer_passed": orch_result.reviewer.passed,
        "package_asset_count": len(asset_manifest),
        "stage_assets": [
            item["asset_type"].value
            for item in asset_manifest
            if item["asset_type"]
            in {
                GeneratedAssetType.PLANNER_STAGE,
                GeneratedAssetType.WRITER_STAGE,
                GeneratedAssetType.REVIEWER_STAGE,
                GeneratedAssetType.FORMATTER_STAGE,
                GeneratedAssetType.RENDERER_INPUT,
            }
        ],
    }
    existing_quality_report = (
        asset_group.quality_report if isinstance(getattr(asset_group, "quality_report", None), dict) else {}
    )
    asset_group.quality_report = {
        **existing_quality_report,
        "reviewer_passed": orch_result.reviewer.passed,
        "reviewer_issues": orch_result.reviewer.issues,
        "optimizer_variant_count": len(orch_result.optimizer.variants),
        "policy_flags": policy_payload,
        "risk_label": policy_payload.get("label", "low"),
        "brand_voice": brand_voice_report,
        "originality": originality_report,
    }

    job.provider_metadata = {
        **(job.provider_metadata or {}),
        "pipeline_stage": "asset_persist",
        "stage_idempotency_key": f"content-job:{job.id}:asset_persist",
    }
    await svc.db.flush()
    # Durable text assets before independent media workers.
    await svc.db.commit()
    return (
        asset_manifest,
        originality_report,
        brand_voice_report,
        policy_payload,
        primary_platform,
        effective_platforms,
    )
