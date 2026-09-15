"""Brief generation, regeneration, and rewrite flows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException

from backend.modules.editorial_briefs.brief_prompt import BRIEF_PROMPT_TEMPLATE
from backend.modules.editorial_briefs.models import BriefStatus, EditorialBrief
from backend.modules.editorial_briefs.schemas import BriefGenerateRequest
from backend.modules.story_intelligence.models import TrendWorkflowState


class BriefGenerationMixin:
    """LLM-backed brief creation and rewrite operations."""

    async def _resolve_brand_constraints(
        self,
        tenant_id: UUID,
        brand_profile_id: UUID | None,
        primary_topic: str,
    ) -> tuple[str, object | None]:
        if not brand_profile_id:
            return "", None
        brand_profile = await self.strategy_repo.get_brand_profile_by_id(tenant_id, brand_profile_id)
        if not brand_profile:
            return "", None
        brand = await self.strategy_repo.get_brand(tenant_id)
        if brand:
            normalized_topic = primary_topic.lower()
            if brand.blocked_topics and any(topic.lower() in normalized_topic for topic in brand.blocked_topics):
                raise HTTPException(status_code=422, detail="Blocked topic for this brand")
            if brand.allowed_topics and not any(topic.lower() in normalized_topic for topic in brand.allowed_topics):
                raise HTTPException(status_code=422, detail="Topic is outside the brand's allowed topics")
        brand_context = (
            f"Brand tone: {brand_profile.tone}. Audience: {brand_profile.audience}. "
            f"Preferred platforms: {', '.join(brand_profile.preferred_platforms)}. "
            f"Guardrails: {json.dumps(brand_profile.guardrails)}."
        )
        return brand_context, brand_profile

    def _default_target_platforms(self, risk_level: str, preferred_platforms: list[str]) -> list[str]:
        if risk_level in {"risky", "sensitive"}:
            return [platform for platform in preferred_platforms if platform in {"x", "threads", "bluesky"}][:3]
        return preferred_platforms[:3] or ["x", "instagram", "threads"]

    async def generate_brief(
        self,
        tenant_id: UUID,
        request: BriefGenerateRequest,
        *,
        actor_user_id: UUID | None = None,
        rewrite_instruction: str = "",
        force_regenerate: bool = False,
    ) -> EditorialBrief:
        # Idempotent: return existing non-rejected brief if present
        existing = await self.repo.get_by_cluster(tenant_id, request.story_cluster_id)
        if existing and not force_regenerate and existing.status not in (
            BriefStatus.REJECTED.value,
            BriefStatus.EXPIRED.value,
        ):
            return existing

        cluster = await self.story_repo.get_cluster(tenant_id, request.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")
        if not cluster.worthy_for_content:
            raise HTTPException(
                status_code=422,
                detail="Cluster is not marked worthy_for_content; resolve risk gates first",
            )
        brand_context, brand_profile = await self._resolve_brand_constraints(
            tenant_id,
            request.brand_profile_id,
            cluster.primary_topic,
        )

        if existing and force_regenerate:
            brief = existing
            brief.brand_profile_id = request.brand_profile_id
            brief.status = BriefStatus.GENERATING.value
            brief.content_vertical = cluster.content_vertical
            brief.risk_level = cluster.risk_level
            brief.headline = cluster.headline
            brief.expires_at = datetime.now(timezone.utc) + timedelta(hours=request.ttl_hours)
            brief.operator_note = None
            brief.approved_by_user_id = None
            brief.actioned_at = None
            await self.db.flush()
        else:
            brief = EditorialBrief(
                tenant_id=tenant_id,
                story_cluster_id=cluster.id,
                brand_profile_id=request.brand_profile_id,
                status=BriefStatus.GENERATING.value,
                content_vertical=cluster.content_vertical,
                risk_level=cluster.risk_level,
                headline=cluster.headline,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=request.ttl_hours),
            )
            brief = await self.repo.create(brief)

        try:
            candidate = await self.story_repo.get_trend_candidate_for_cluster(tenant_id, cluster.id)
            evidence_links = candidate.evidence_links if candidate else []
            extracted_claims = candidate.extracted_claims if candidate else []
            preferred_platforms_raw = getattr(brand_profile, "preferred_platforms", None) if brand_profile else None
            preferred_platforms = (
                list(preferred_platforms_raw)
                if isinstance(preferred_platforms_raw, list)
                else ["x", "instagram", "threads"]
            )

            prompt = BRIEF_PROMPT_TEMPLATE.format(
                headline=cluster.headline,
                summary=cluster.summary,
                primary_topic=cluster.primary_topic,
                content_vertical=cluster.content_vertical,
                risk_level=cluster.risk_level,
                keywords=cluster.explainability.get("keywords", ""),
                evidence_links=", ".join(evidence_links),
                claims=" | ".join(extracted_claims[:5]),
                brand_context=brand_context,
                rewrite_instruction=rewrite_instruction or "None",
            )
            parsed = await self.llm.generate_structured_json(
                prompt,
                schema_hint={
                    "topic_title": cluster.headline,
                    "why_now": cluster.summary[:220],
                    "angle": "",
                    "talking_points": [],
                    "recommended_format": "text",
                    "target_platforms": self._default_target_platforms(cluster.risk_level, preferred_platforms),
                    "evidence_links": evidence_links[:5],
                    "audience_segment": str(getattr(brand_profile, "audience", "general social audience")),
                    "platform_recommendations": preferred_platforms[:3],
                    "tone_guidance": str(getattr(brand_profile, "tone", "authoritative")),
                    "cta_strategy": str(getattr(brand_profile, "default_cta", "Follow for more updates")),
                    "caveats": [],
                    "suggested_formats": [],
                    "risk_notes": "",
                },
                max_tokens=600,
                temperature=0.4,
                task="editorial_brief",
            )

            brief.headline = parsed.get("topic_title", cluster.headline)
            brief.why_now = parsed.get("why_now", cluster.summary[:220])
            brief.angle = parsed.get("angle", "")
            brief.talking_points = parsed.get("talking_points", [])
            brief.recommended_format = parsed.get("recommended_format", "text")
            brief.target_platforms = parsed.get(
                "target_platforms",
                self._default_target_platforms(cluster.risk_level, preferred_platforms),
            )
            brief.evidence_links = parsed.get("evidence_links", evidence_links[:5])
            brief.audience_segment = parsed.get(
                "audience_segment",
                str(getattr(brand_profile, "audience", "general social audience")),
            )
            brief.platform_recommendations = parsed.get("platform_recommendations", brief.target_platforms)
            brief.tone_guidance = parsed.get("tone_guidance", str(getattr(brand_profile, "tone", "authoritative")))
            brief.cta_strategy = parsed.get(
                "cta_strategy",
                str(getattr(brand_profile, "default_cta", "Follow for more updates")),
            )
            brief.caveats = parsed.get("caveats", [])
            brief.suggested_formats = parsed.get(
                "suggested_formats",
                ["short post", "thread", "caption"]
                if brief.recommended_format == "text"
                else ["script", "caption", "hook"],
            )
            brief.risk_notes = parsed.get("risk_notes", "")
            brief.status = BriefStatus.READY.value
            cluster.workflow_state = TrendWorkflowState.BRIEF_READY.value
            brief.rewrite_context = {
                "instruction": rewrite_instruction or "",
                "actor_user_id": str(actor_user_id) if actor_user_id else "",
            }
            brief.generation_trace = {
                "raw_output": json.dumps(parsed)[:2000],
                "candidate_id": str(candidate.id) if candidate else "",
                "risk_label": str(
                    getattr(candidate, "score_explanation", {}).get("review_risk_label", "low")
                )
                if candidate
                else "low",
            }
        except Exception as exc:  # noqa: BLE001
            brief.status = BriefStatus.PENDING.value  # reset — can retry
            brief.generation_trace = {"error": str(exc)}

        await self.db.flush()
        return brief
