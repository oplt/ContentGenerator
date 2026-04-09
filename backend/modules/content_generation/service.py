from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from backend.modules.audit.service import AuditService
from backend.modules.editorial_briefs.models import BriefStatus
from backend.modules.editorial_briefs.repository import EditorialBriefRepository
from backend.modules.inference.orchestrator import ContentOrchestrator
from backend.modules.content_generation.models import (
    ContentJob,
    ContentJobStatus,
    ContentJobType,
    ContentRevision,
    GeneratedAsset,
    GeneratedAssetGroup,
    GeneratedAssetGroupStatus,
    GeneratedAssetType,
    VideoStage,
)
from backend.modules.content_generation.repository import ContentGenerationRepository
from backend.modules.content_generation.schemas import ContentJobResponse, GeneratedAssetResponse
from backend.modules.content_strategy.models import ContentFormat
from backend.modules.content_strategy.repository import ContentStrategyRepository
from backend.modules.fact_review.service import FactRiskReviewService
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster, TrendWorkflowState
from backend.modules.inference.providers import get_llm_provider
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.video_pipeline.service import VideoPipelineService
from backend.modules.video_pipeline.schemas import BrandingConfig, MediaSequenceItem, RenderPreset, RendererInput, VisualSegment


PLATFORM_LIMITS = {
    "x": 280,
    "bluesky": 300,
    "instagram": 1000,
    "tiktok": 400,
    "youtube_title": 95,
    "youtube_description": 1000,
}


class ContentGenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContentGenerationRepository(db)
        self.plan_repo = ContentStrategyRepository(db)
        self.story_repo = StoryIntelligenceRepository(db)
        self.audit = AuditService(db)
        self.video_pipeline = VideoPipelineService(db)
        self.llm = get_llm_provider()
        self.fact_review = FactRiskReviewService()

    def _fact_review_service(self) -> FactRiskReviewService:
        if not hasattr(self, "fact_review") or self.fact_review is None:
            self.fact_review = FactRiskReviewService()
        return self.fact_review

    def _prompt_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "prompts" / "text_generation" / "v1"

    def _load_template(self, name: str) -> str:
        template_path = self._prompt_dir() / f"{name}.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return "Write grounded platform content from the supplied facts."

    def _trim(self, text: str, limit: int) -> str:
        return text[: limit - 3] + "..." if len(text) > limit else text

    def _build_hashtags(self, topic: str, strategy: str) -> str:
        base = [f"#{topic.replace(' ', '')}"]
        if strategy == "aggressive":
            base.extend(["#TrendingNow", "#BreakingNews"])
        return " ".join(base[:3])

    def _grounding_block(
        self,
        cluster: StoryCluster,
        source_articles: list[NormalizedArticle],
        feedback: str | None,
    ) -> str:
        article_snippets = "\n".join(
            f"- [{a.source_name}] {a.title}: {(a.summary or a.body or '')[:300]}"
            for a in source_articles[:3]
        )
        feedback_note = f"\nRevision instruction: {feedback}" if feedback else ""
        return (
            f"VERIFIED FACTS (use only these, do not add claims not present here):\n"
            f"Headline: {cluster.headline}\n"
            f"Summary: {cluster.summary}\n"
            f"Key entities: {cluster.explainability.get('keywords', cluster.primary_topic)}\n"
            f"Source articles:\n{article_snippets}"
            f"{feedback_note}"
        )

    def _hallucination_guard(self, text: str, entities: list[str]) -> bool:
        """Return True if at least half of the key entities appear in the generated text."""
        if not entities:
            return True
        text_lower = text.lower()
        matches = sum(1 for e in entities if e.lower() in text_lower)
        return matches >= max(1, len(entities) // 2)

    async def _draft_platform_variants(
        self,
        *,
        platform: str,
        cluster: StoryCluster,
        tone: str,
        cta: str | None,
        hashtags_strategy: str,
        source_articles: list[NormalizedArticle],
        feedback: str | None = None,
    ) -> list[tuple[str, str]]:
        hashtags = self._build_hashtags(cluster.primary_topic, hashtags_strategy)
        limit = PLATFORM_LIMITS.get("youtube_description" if platform == "youtube" else platform, 280)
        grounding = self._grounding_block(cluster, source_articles, feedback)
        template = self._load_template(platform)

        if platform == "youtube":
            title_prompt = (
                f"{grounding}\n\n"
                f"Write a YouTube video title (max {PLATFORM_LIMITS['youtube_title']} chars). "
                f"Tone: {tone}. Be accurate, not clickbait."
            )
            desc_prompt = (
                f"{grounding}\n\n"
                f"Write a YouTube video description (max {PLATFORM_LIMITS['youtube_description']} chars). "
                f"Tone: {tone}. Include {cta or 'Subscribe for more'}. "
                f"End with: 'Sources available on request.'"
            )
            title = self._trim(await self.llm.generate(title_prompt, max_tokens=50, temperature=0.5), PLATFORM_LIMITS["youtube_title"])
            description = self._trim(await self.llm.generate(desc_prompt, max_tokens=400, temperature=0.6), PLATFORM_LIMITS["youtube_description"])
            return [("title", title), ("description", description)]

        prompt = (
            f"{template}\n\n"
            f"{grounding}\n\n"
            f"Platform: {platform} (max {limit} characters per variant)\n"
            f"Tone: {tone}\n"
            f"CTA: {cta or 'Follow for more'}\n"
            f"Hashtags to include: {hashtags}\n\n"
            f"Write exactly 3 variants labeled A, B, C. "
            f"Each variant must stand alone and fit within {limit} characters. "
            f"Only use facts from the VERIFIED FACTS block above."
        )
        response = await self.llm.generate(prompt, max_tokens=600, temperature=0.7)

        # Parse A/B/C from the response; fall back to slicing if format is off
        variants = self._parse_abc_variants(response, cluster, hashtags, cta, limit)
        entities = cluster.explainability.get("keywords", "").split(", ")[:4]
        validated = []
        for label, content in variants:
            if self._hallucination_guard(content, entities):
                validated.append((label, self._trim(content, limit)))
            else:
                # Entity check failed — fall back to template-safe variant
                safe = self._trim(f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip(), limit)
                validated.append((label, safe))
        return validated

    def _parse_abc_variants(
        self,
        response: str,
        cluster: StoryCluster,
        hashtags: str,
        cta: str | None,
        limit: int,
    ) -> list[tuple[str, str]]:
        """Extract A/B/C variants from LLM response. Falls back to template on parse failure."""
        import re
        parts: dict[str, str] = {}
        for match in re.finditer(r"(?:^|\n)\s*([ABC])[):.]\s*(.+?)(?=\n\s*[ABC][):.]|\Z)", response, re.DOTALL):
            label, text = match.group(1), match.group(2).strip()
            parts[label] = text
        if len(parts) >= 2:
            return [(label, parts[label]) for label in ("A", "B", "C") if label in parts]
        # Fallback templates
        base = f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip()
        return [
            ("A", base),
            ("B", f"{cluster.headline}\n{cluster.summary}\n{cta or 'Follow for more.'} {hashtags}"),
            ("C", f"{cluster.primary_topic.title()} update: {cluster.summary} {hashtags}"),
        ]

    async def _create_asset(
        self,
        *,
        tenant_id: UUID,
        asset_group_id: UUID | None,
        content_job_id: UUID,
        asset_type: GeneratedAssetType,
        platform: str | None,
        variant_label: str | None,
        text_content: str,
        source_trace: dict[str, str],
        mime_type: str = "text/markdown",
        asset_metadata: dict[str, str] | None = None,
    ) -> GeneratedAsset:
        asset = GeneratedAsset(
            tenant_id=tenant_id,
            asset_group_id=asset_group_id,
            content_job_id=content_job_id,
            asset_type=asset_type.value,
            platform=platform,
            variant_label=variant_label,
            mime_type=mime_type,
            text_content=text_content,
            asset_metadata=asset_metadata or {"template_version": "v1"},
            source_trace=source_trace,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    def _serialize_payload(self, payload: object) -> str:
        return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()

    def _sentence_split(self, text: str) -> list[str]:
        chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
        return chunks or ([text.strip()] if text.strip() else [])

    def _build_thread(self, headline: str, summary: str, talking_points: list[str], cta: str) -> str:
        thread_parts = [headline.strip()]
        thread_parts.extend(point.strip() for point in talking_points[:3] if point.strip())
        if summary.strip():
            thread_parts.append(summary.strip())
        if cta.strip():
            thread_parts.append(cta.strip())
        return "\n".join(f"{index}. {part}" for index, part in enumerate(thread_parts[:5], start=1))

    def _build_fact_checklist(
        self,
        *,
        cluster: StoryCluster,
        source_articles: list[NormalizedArticle],
        claims: list[str],
        evidence_links: list[str] | None = None,
    ) -> dict[str, object]:
        return self._fact_review_service().build_fact_checklist(
            topic=cluster.primary_topic,
            topic_risk_level=getattr(cluster, "risk_level", "safe") or "safe",
            claims=claims or [cluster.summary or cluster.headline],
            source_articles=source_articles,
            evidence_links=evidence_links or [],
        )

    def _build_attribution_list(
        self,
        *,
        brief,
        source_articles: list[NormalizedArticle],
    ) -> dict[str, object]:
        links = []
        for article in source_articles[:8]:
            links.append(
                {
                    "source": article.source_name,
                    "title": article.title,
                    "url": article.canonical_url,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                }
            )
        for url in getattr(brief, "evidence_links", []) or []:
            if not any(link["url"] == url for link in links):
                links.append({"source": "brief_evidence", "title": url, "url": url, "published_at": None})
        return {"count": len(links), "links": links}

    def _build_policy_flags(
        self,
        *,
        cluster: StoryCluster,
        brief,
        orch_result,
        fact_checklist: dict[str, object],
        source_articles: list[NormalizedArticle],
        effective_platforms: list[str],
    ) -> dict[str, object]:
        generated_texts = {
            platform: str(orch_result.writer.drafts.get(platform) or "").strip()
            for platform in effective_platforms
            if str(orch_result.writer.drafts.get(platform) or "").strip()
        }
        review = self._fact_review_service().review_generated_package(
            content_vertical=getattr(cluster, "content_vertical", "general") or "general",
            headline=cluster.headline,
            summary=cluster.summary or "",
            topic=cluster.primary_topic,
            topic_risk_level=getattr(cluster, "risk_level", "safe") or "safe",
            claims=list(orch_result.extractor.claims or []),
            keywords=[part.strip() for part in cluster.explainability.get("keywords", "").split(",") if part.strip()],
            source_articles=source_articles,
            evidence_links=list(getattr(brief, "evidence_links", []) or []),
            generated_texts=generated_texts,
            reviewer_issues=list(orch_result.reviewer.issues or []),
        )
        # Preserve the externally passed fact_checklist as the persisted reference.
        review["policy_flags"]["fact_checklist_topic"] = fact_checklist.get("topic")
        return review["policy_flags"]

    def _build_brand_voice_report(
        self,
        *,
        plan,
        brief,
        profile,
        effective_tone: str,
        platforms: list[str],
        asset_manifest: list[dict[str, object]],
    ) -> dict[str, object]:
        profile_platforms = getattr(profile, "preferred_platforms", []) if profile is not None else []
        if not isinstance(profile_platforms, list):
            profile_platforms = []
        plan_platforms = plan.target_platforms if isinstance(getattr(plan, "target_platforms", []), list) else []
        target_platforms = list(profile_platforms or plan_platforms)

        profile_tone = getattr(profile, "tone", None) if profile is not None else None
        brief_tone = getattr(brief, "tone_guidance", None)
        expected_tone = (
            profile_tone if isinstance(profile_tone, str) else
            brief_tone if isinstance(brief_tone, str) else
            plan.tone
        )

        profile_cta = getattr(profile, "default_cta", None) if profile is not None else None
        brief_cta = getattr(brief, "cta_strategy", "")
        expected_cta = (
            profile_cta if isinstance(profile_cta, str) else
            plan.recommended_cta if isinstance(getattr(plan, "recommended_cta", None), str) else
            brief_cta if isinstance(brief_cta, str) else
            ""
        )
        sample_text = " ".join(
            str(asset.get("content", "")) for asset in asset_manifest[:4] if str(asset.get("content", "")).strip()
        ).lower()
        issues = []
        if expected_tone and effective_tone != expected_tone:
            issues.append(f"Generation tone '{effective_tone}' differs from profile tone '{expected_tone}'")
        if target_platforms:
            missing_platforms = sorted(set(target_platforms) - set(platforms))
            if missing_platforms:
                issues.append(f"Missing preferred platforms: {', '.join(missing_platforms)}")
        if expected_cta and expected_cta.lower()[:24] not in sample_text:
            issues.append("Expected CTA is weakly represented across the package")
        return {
            "compliant": not issues,
            "expected_tone": expected_tone,
            "effective_tone": effective_tone,
            "preferred_platforms": target_platforms,
            "issues": issues,
        }

    def _measure_originality(
        self,
        *,
        asset_manifest: list[dict[str, object]],
        source_articles: list[NormalizedArticle],
    ) -> dict[str, object]:
        candidate_texts = [str(asset.get("content", "")).strip() for asset in asset_manifest if str(asset.get("content", "")).strip()]
        source_snippets = [
            ((article.summary or article.body or article.title or "")[:500]).strip()
            for article in source_articles[:5]
            if (article.summary or article.body or article.title)
        ]
        max_source_similarity = 0.0
        for text in candidate_texts[:12]:
            for source_text in source_snippets:
                max_source_similarity = max(
                    max_source_similarity,
                    SequenceMatcher(None, self._normalize_text(text), self._normalize_text(source_text)).ratio(),
                )
        max_internal_similarity = 0.0
        for index, text in enumerate(candidate_texts):
            for other in candidate_texts[index + 1 :]:
                max_internal_similarity = max(
                    max_internal_similarity,
                    SequenceMatcher(None, self._normalize_text(text), self._normalize_text(other)).ratio(),
                )
        repeated_phrases = []
        phrase_counts: dict[str, int] = {}
        for text in candidate_texts:
            for sentence in self._sentence_split(text):
                normalized = self._normalize_text(sentence)
                if len(normalized.split()) < 4:
                    continue
                phrase_counts[normalized] = phrase_counts.get(normalized, 0) + 1
        for phrase, count in phrase_counts.items():
            if count > 2:
                repeated_phrases.append({"phrase": phrase[:120], "count": count})
        blocked = max_source_similarity >= 0.93
        return {
            "blocked": blocked,
            "label": "blocked" if blocked else ("high" if max_source_similarity >= 0.85 else "low"),
            "max_source_similarity": round(max_source_similarity, 4),
            "max_internal_similarity": round(max_internal_similarity, 4),
            "repeated_phrases": repeated_phrases[:10],
        }

    def _build_renderer_input_payload(
        self,
        *,
        platform: str,
        headline: str,
        summary: str,
        script: str,
        cta: str,
        talking_points: list[str],
        profile=None,
    ) -> dict[str, object]:
        subtitle_lines = self._sentence_split(script)[:8]
        visual_segments = [
            VisualSegment(
                segment=index + 1,
                prompt=point,
                duration_seconds=2.0 if index else 2.5,
            )
            for index, point in enumerate((talking_points or subtitle_lines or [headline])[:6])
        ]
        palette_value = getattr(profile, "visual_style", {}).get("palette", "") if profile is not None else ""
        palette = [part.strip() for part in str(palette_value).replace("|", ",").split(",") if part.strip()]
        branding = BrandingConfig(
            palette=palette[:3] or ["#0f172a", "#1d4ed8", "#f8fafc"],
            text_color=str(getattr(profile, "visual_style", {}).get("text_color", "#f8fafc")) if profile is not None else "#f8fafc",
            accent_color=str(getattr(profile, "visual_style", {}).get("accent_color", "#38bdf8")) if profile is not None else "#38bdf8",
            progress_bar=True,
            subtitle_burn_in=True,
            overlay_opacity=float(getattr(profile, "visual_style", {}).get("overlay_opacity", 0.28)) if profile is not None else 0.28,
            font_family=str(getattr(profile, "visual_style", {}).get("font_family", "Sans")) if profile is not None else "Sans",
            intro_text=headline,
            outro_text=cta or str(getattr(profile, "default_cta", "") or ""),
        )
        preset = (
            RenderPreset.SQUARE if platform == "instagram"
            else RenderPreset.HORIZONTAL if platform in {"youtube", "youtube_shorts"} else RenderPreset.VERTICAL
        )
        media_sequence = [
            MediaSequenceItem(
                kind="title",
                duration_seconds=2.0,
                background_color=branding.palette[0],
                text=headline,
            ),
            MediaSequenceItem(
                kind="summary",
                duration_seconds=2.0,
                background_color=branding.palette[1] if len(branding.palette) > 1 else branding.palette[0],
                text=summary or headline,
            ),
        ]
        media_sequence.extend(
            MediaSequenceItem(
                kind="segment",
                duration_seconds=segment.duration_seconds,
                background_color=branding.palette[(segment.segment + 1) % len(branding.palette)],
                text=segment.prompt,
            )
            for segment in visual_segments
        )
        if branding.outro_text:
            media_sequence.append(
                MediaSequenceItem(
                    kind="outro",
                    duration_seconds=2.0,
                    background_color=branding.palette[0],
                    text=branding.outro_text,
                )
            )
        payload = RendererInput(
            platform=platform,
            script=script,
            subtitles=subtitle_lines,
            voiceover_script=script,
            visual_segments=visual_segments,
            media_sequence=media_sequence,
            title_card=headline,
            summary_card=summary,
            cta=cta,
            branding=branding,
            preset=preset,
            output_duration_seconds=max(8.0, sum(item.duration_seconds for item in media_sequence)),
            preview_duration_seconds=4.0,
        )
        return payload.model_dump(mode="json")

    def _build_platform_asset_specs(
        self,
        *,
        cluster: StoryCluster,
        brief,
        plan,
        profile,
        orch_result,
        effective_platforms: list[str],
        primary_platform: str,
        source_articles: list[NormalizedArticle],
    ) -> list[dict[str, object]]:
        hashtags = orch_result.writer.hashtags or self._build_hashtags(cluster.primary_topic, plan.hashtags_strategy).split()
        safer_variant = orch_result.reviewer.revised_draft or f"{cluster.headline}. {cluster.summary}".strip()
        thread_text = self._build_thread(
            cluster.headline,
            cluster.summary or "",
            list(getattr(brief, "talking_points", []) or orch_result.planner.structure or []),
            plan.recommended_cta or "",
        )
        evidence_lines = [
            f"- {article.source_name}: {article.title} ({article.canonical_url})"
            for article in source_articles[:5]
        ] or [f"- {url}" for url in getattr(brief, "evidence_links", [])[:5]]
        fact_checklist = self._build_fact_checklist(
            cluster=cluster,
            source_articles=source_articles,
            claims=list(orch_result.extractor.claims or []),
            evidence_links=list(getattr(brief, "evidence_links", []) or []),
        )
        attribution_list = self._build_attribution_list(brief=brief, source_articles=source_articles)
        policy_flags = self._build_policy_flags(
            cluster=cluster,
            brief=brief,
            orch_result=orch_result,
            fact_checklist=fact_checklist,
            source_articles=source_articles,
            effective_platforms=effective_platforms,
        )

        manifest: list[dict[str, object]] = [
            {
                "asset_type": GeneratedAssetType.PLANNER_STAGE,
                "platform": None,
                "variant_label": "planner",
                "content": self._serialize_payload(orch_result.planner.model_dump()),
                "mime_type": "application/json",
                "asset_metadata": {"stage": "planner"},
            },
            {
                "asset_type": GeneratedAssetType.WRITER_STAGE,
                "platform": None,
                "variant_label": "writer",
                "content": self._serialize_payload(orch_result.writer.model_dump()),
                "mime_type": "application/json",
                "asset_metadata": {"stage": "writer"},
            },
            {
                "asset_type": GeneratedAssetType.REVIEWER_STAGE,
                "platform": None,
                "variant_label": "reviewer",
                "content": self._serialize_payload(orch_result.reviewer.model_dump()),
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
                "content": self._serialize_payload(fact_checklist),
                "mime_type": "application/json",
                "asset_metadata": {"report": "fact_checklist"},
            },
            {
                "asset_type": GeneratedAssetType.ATTRIBUTION_LIST,
                "platform": None,
                "variant_label": "attribution",
                "content": self._serialize_payload(attribution_list),
                "mime_type": "application/json",
                "asset_metadata": {"report": "attribution"},
            },
            {
                "asset_type": GeneratedAssetType.POLICY_FLAGS,
                "platform": None,
                "variant_label": "policy",
                "content": self._serialize_payload(policy_flags),
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
                        "content": self._serialize_payload(orch_result.optimizer.variants[:3] or [orch_result.planner.hook]),
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
            concise = self._trim(orch_result.writer.drafts.get("bluesky") or orch_result.final_draft or cluster.headline, PLATFORM_LIMITS["bluesky"])
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
                        "content": self._trim(thread_text, PLATFORM_LIMITS["bluesky"]),
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
                *(list(getattr(brief, "talking_points", []) or [])[:3] or self._sentence_split(cluster.summary or cluster.headline)[:3]),
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
                        "content": self._serialize_payload(carousel_slides),
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
            script = self._build_thread(cluster.headline, cluster.summary or "", list(getattr(brief, "talking_points", []) or []), plan.recommended_cta or "")
            subtitle_plan = self._sentence_split(script)
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
                        "content": self._serialize_payload(subtitle_plan[:6]),
                        "mime_type": "application/json",
                        "asset_metadata": {"platform_package": "tiktok"},
                    },
                    {
                        "asset_type": GeneratedAssetType.SHOT_LIST,
                        "platform": "tiktok",
                        "variant_label": "shot_list",
                        "content": self._serialize_payload((getattr(brief, "talking_points", []) or subtitle_plan)[:6]),
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
            script = self._build_thread(cluster.headline, cluster.summary or "", list(getattr(brief, "talking_points", []) or []), plan.recommended_cta or "")
            title_variants = [
                self._trim(orch_result.planner.hook or cluster.headline, PLATFORM_LIMITS["youtube_title"]),
                self._trim(f"{cluster.primary_topic.title()}: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
                self._trim(f"What changed: {cluster.headline}", PLATFORM_LIMITS["youtube_title"]),
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
                        "content": self._serialize_payload(title_variants),
                        "mime_type": "application/json",
                        "asset_metadata": {"platform_package": youtube_platform},
                    },
                    {
                        "asset_type": GeneratedAssetType.DESCRIPTION,
                        "platform": youtube_platform,
                        "variant_label": "description",
                        "content": self._trim(
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
                        "content": self._serialize_payload(self._sentence_split(script)[:6]),
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
                "content": self._serialize_payload(formatter_manifest),
                "mime_type": "application/json",
                "asset_metadata": {"stage": "formatter"},
            }
        )

        for platform in sorted(platform_set.intersection({"instagram", "tiktok", "youtube", "youtube_shorts"})):
            renderer_payload = self._build_renderer_input_payload(
                platform=platform,
                headline=cluster.headline,
                summary=cluster.summary or "",
                script=self._build_thread(
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
                    "content": self._serialize_payload(renderer_payload),
                    "mime_type": "application/json",
                    "asset_metadata": {"stage": "renderer_input"},
                }
            )

        return manifest

    async def generate(self, *, tenant_id: UUID, plan_id: UUID, feedback: str | None = None, revision_of_job_id: UUID | None = None) -> ContentJob:
        plan = await self.plan_repo.get_content_plan(tenant_id, plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        if plan.decision != "generate":
            raise HTTPException(status_code=400, detail="Content plan is not approved for generation")
        cluster = await self.story_repo.get_cluster(tenant_id, plan.story_cluster_id)
        if not cluster:
            raise HTTPException(status_code=404, detail="Story cluster not found")

        # Gate: require an approved editorial brief before generating content
        brief_repo = EditorialBriefRepository(self.db)
        brief = await brief_repo.get_by_cluster(tenant_id, plan.story_cluster_id)
        if not brief or brief.status != BriefStatus.APPROVED.value:
            raise HTTPException(
                status_code=422,
                detail=(
                    "An approved editorial brief is required before generating content. "
                    "Create and approve a brief for this story cluster first."
                ),
            )

        job = await self.repo.create_job(
            ContentJob(
                tenant_id=tenant_id,
                content_plan_id=plan.id,
                revision_of_job_id=revision_of_job_id,
                job_type=ContentJobType.REVISION.value if feedback else plan.content_format,
                status=ContentJobStatus.RUNNING.value,
                stage=VideoStage.QUEUED.value,
                progress=5,
                feedback=feedback,
                grounding_bundle={
                    "headline": cluster.headline,
                    "summary": cluster.summary,
                    "topic": cluster.primary_topic,
                },
                started_at=datetime.now(timezone.utc),
            )
        )
        asset_group = await self.repo.create_asset_group(
            GeneratedAssetGroup(
                tenant_id=tenant_id,
                content_job_id=job.id,
                content_plan_id=plan.id,
                status=GeneratedAssetGroupStatus.CREATED.value,
                platform_targets=plan.target_platforms,
                asset_types=[],
                generation_trace={"brief_id": str(brief.id), "revision_of_job_id": str(revision_of_job_id) if revision_of_job_id else None},
                quality_report={},
            )
        )
        cluster.workflow_state = TrendWorkflowState.ASSET_GENERATION.value

        # Fetch source articles for grounding
        source_articles = await self.story_repo.list_normalized_for_cluster(cluster.id)
        body_text = "\n".join(
            (a.body or a.summary or "")[:600] for a in source_articles[:3]
        )

        # ── Optimization-informed tone selection ─────────────────────────────
        primary_platform = plan.target_platforms[0] if plan.target_platforms else "x"
        effective_tone = plan.tone
        try:
            from backend.modules.analytics.optimization import OptimizationService
            opt_svc = OptimizationService(self.db)
            recommended_tone = await opt_svc.best_tone_for_platform(tenant_id, primary_platform)
            if recommended_tone:
                effective_tone = recommended_tone
        except Exception:
            pass  # Fall back to plan tone if optimization data is unavailable

        profile = None
        if getattr(plan, "brand_profile_id", None):
            try:
                profile = await self.plan_repo.get_brand_profile_by_id(tenant_id, plan.brand_profile_id)
            except Exception:
                profile = None
        if not profile:
            try:
                profile = await self.plan_repo.get_brand_profile(tenant_id)
            except Exception:
                profile = None

        # ── Multi-role orchestration pipeline ───────────────────────────────
        orchestrator = ContentOrchestrator(llm=self.llm)
        orch_result = await orchestrator.run(
            headline=cluster.headline,
            summary=cluster.summary or "",
            body=body_text,
            angle=brief.angle or "",
            talking_points=list(brief.talking_points or []),
            content_vertical=getattr(cluster, "content_vertical", None) or "general",
            risk_level=getattr(cluster, "risk_level", None) or "safe",
            tone=effective_tone,
            audience="Social media audience",
            preferred_platforms=plan.target_platforms,
            hashtags_strategy=plan.hashtags_strategy or "balanced",
            cta=plan.recommended_cta or "",
            worthiness_threshold=0.35,
        )

        # ── High-risk reviewer enforcement ────────────────────────────────────
        cluster_risk = getattr(cluster, "risk_level", "safe") or "safe"
        if cluster_risk in ("risky", "high_risk") and not orch_result.reviewer.passed:
            if not orch_result.reviewer.revised_draft:
                job.status = ContentJobStatus.FAILED.value
                job.error_message = (
                    "Content reviewer rejected draft for high-risk story: "
                    + "; ".join(orch_result.reviewer.issues)
                )
                await self.db.flush()
                raise HTTPException(
                    status_code=422,
                    detail=job.error_message,
                )

        # ── Create assets from orchestrator output ────────────────────────────
        source_trace = {
            "story_cluster_id": str(cluster.id),
            "headline": cluster.headline,
            "keywords": cluster.explainability.get("keywords", ""),
            "source_article_count": str(len(source_articles)),
            "orchestrator_scorer_composite": str(orch_result.scorer.composite),
            "orchestrator_reviewer_passed": str(orch_result.reviewer.passed),
            "orchestrator_extractor_vertical": orch_result.extractor.content_vertical,
        }

        effective_platforms = list(orch_result.planner.target_platforms or plan.target_platforms)
        primary_platform = effective_platforms[0] if effective_platforms else "x"
        asset_manifest = self._build_platform_asset_specs(
            cluster=cluster,
            brief=brief,
            plan=plan,
            profile=profile,
            orch_result=orch_result,
            effective_platforms=effective_platforms,
            primary_platform=primary_platform,
            source_articles=source_articles,
        )
        originality_report = self._measure_originality(
            asset_manifest=asset_manifest,
            source_articles=source_articles,
        )
        brand_voice_report = self._build_brand_voice_report(
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
                    "content": self._serialize_payload(brand_voice_report),
                    "mime_type": "application/json",
                    "asset_metadata": {"report": "brand_voice"},
                },
                {
                    "asset_type": GeneratedAssetType.ORIGINALITY_REPORT,
                    "platform": None,
                    "variant_label": "originality",
                    "content": self._serialize_payload(originality_report),
                    "mime_type": "application/json",
                    "asset_metadata": {"report": "originality"},
                },
            ]
        )
        for asset_spec in asset_manifest:
            await self._create_asset(
                tenant_id=tenant_id,
                asset_group_id=asset_group.id,
                content_job_id=job.id,
                asset_type=asset_spec["asset_type"],
                platform=asset_spec["platform"],
                variant_label=asset_spec["variant_label"],
                text_content=asset_spec["content"],
                source_trace=source_trace,
                mime_type=asset_spec["mime_type"],
                asset_metadata=asset_spec.get("asset_metadata"),
            )

        # Persist inference trace in the job for explainability
        job.grounding_bundle = {
            **job.grounding_bundle,
            "risk_review": json.loads(
                next(
                    item["content"]
                    for item in asset_manifest
                    if item["asset_type"] == GeneratedAssetType.POLICY_FLAGS
                )
            ),
            "risk_label": str(
                json.loads(
                    next(
                        item["content"]
                        for item in asset_manifest
                        if item["asset_type"] == GeneratedAssetType.POLICY_FLAGS
                    )
                ).get("label", "low")
            ),
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
                if item["asset_type"] in {
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
            "policy_flags": json.loads(
                next(
                    item["content"]
                    for item in asset_manifest
                    if item["asset_type"] == GeneratedAssetType.POLICY_FLAGS
                )
            ),
            "risk_label": json.loads(
                next(
                    item["content"]
                    for item in asset_manifest
                    if item["asset_type"] == GeneratedAssetType.POLICY_FLAGS
                )
            ).get("label", "low"),
            "brand_voice": brand_voice_report,
            "originality": originality_report,
        }
        policy_payload = asset_group.quality_report["policy_flags"]

        # ── Cover image generation ────────────────────────────────────────────
        try:
            from backend.modules.content_generation.image_service import ImageGenerationService
            img_svc = ImageGenerationService(self.db)
            await img_svc.generate_for_job(
                tenant_id=tenant_id,
                job_id=job.id,
                headline=cluster.headline,
                primary_topic=cluster.primary_topic,
                keywords=cluster.explainability.get("keywords", ""),
                platform=primary_platform,
            )
        except Exception as exc:
            logger.warning("image_generation_failed job=%s error=%s", job.id, exc)

        # ── Voiceover generation ──────────────────────────────────────────────
        try:
            from backend.modules.content_generation.tts_service import TTSService
            tts_svc = TTSService(self.db)
            await tts_svc.generate_for_job(
                tenant_id=tenant_id,
                job_id=job.id,
                headline=cluster.headline,
                summary=cluster.summary or "",
                cta=plan.recommended_cta or "",
                platform=primary_platform,
            )
        except Exception as exc:
            logger.warning("tts_generation_failed job=%s error=%s", job.id, exc)

        if plan.content_format in {ContentFormat.VIDEO.value, ContentFormat.BOTH.value}:
            job.stage = VideoStage.RESEARCHING.value
            job.progress = 35
            await self.video_pipeline.run(job=job, cluster=cluster)

        job.status = ContentJobStatus.COMPLETED.value
        job.stage = VideoStage.COMPLETED.value
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        if originality_report["blocked"] or policy_payload.get("blocked"):
            asset_group.status = GeneratedAssetGroupStatus.REJECTED.value
            cluster.workflow_state = TrendWorkflowState.ASSET_GENERATION.value
        else:
            asset_group.status = GeneratedAssetGroupStatus.REVIEWED.value
            cluster.workflow_state = TrendWorkflowState.ASSET_REVIEW.value
        await self.audit.record(
            tenant_id=tenant_id,
            actor_user_id=None,
            action="content.generated",
            entity_type="generated_asset_group",
            entity_id=str(asset_group.id),
            message="Content generation job completed",
            payload={"content_plan_id": str(plan.id), "content_job_id": str(job.id)},
            payload_schema="generated_asset_group.v1",
            outcome="completed",
        )
        await self.db.flush()
        return job

    async def regenerate_with_feedback(
        self,
        *,
        tenant_id: UUID,
        job_id: UUID,
        feedback: str,
        requested_by_user_id: UUID | None,
        source_channel: str,
    ) -> ContentJob:
        original_job = await self.repo.get_job(tenant_id, job_id)
        if not original_job:
            raise HTTPException(status_code=404, detail="Content job not found")
        latest_revision_number = 1
        await self.repo.create_revision(
            ContentRevision(
                tenant_id=tenant_id,
                content_job_id=original_job.id,
                revision_number=latest_revision_number,
                feedback=feedback,
                source_channel=source_channel,
                requested_by_user_id=requested_by_user_id,
                status="processing",
                diff_summary="Regenerated copy using provided feedback",
                revision_payload={"feedback": feedback},
            )
        )
        return await self.generate(
            tenant_id=tenant_id,
            plan_id=original_job.content_plan_id,
            feedback=feedback,
            revision_of_job_id=original_job.id,
        )

    async def regenerate_asset_group(
        self,
        *,
        tenant_id: UUID,
        asset_group_id: UUID,
        instruction: str,
        requested_by_user_id: UUID | None,
        source_channel: str,
    ) -> ContentJob:
        asset_group = await self.repo.get_asset_group(tenant_id, asset_group_id)
        if not asset_group:
            raise HTTPException(status_code=404, detail="Generated asset group not found")
        original_job = await self.repo.get_job(tenant_id, asset_group.content_job_id)
        if not original_job:
            raise HTTPException(status_code=404, detail="Content job not found")

        asset_group.status = GeneratedAssetGroupStatus.REGENERATED.value
        asset_group.generation_trace = {
            **asset_group.generation_trace,
            "regeneration_requested_at": datetime.now(timezone.utc).isoformat(),
            "regeneration_instruction": instruction,
            "regeneration_source_channel": source_channel,
        }
        await self.repo.create_revision(
            ContentRevision(
                tenant_id=tenant_id,
                content_job_id=original_job.id,
                revision_number=1,
                feedback=instruction,
                source_channel=source_channel,
                requested_by_user_id=requested_by_user_id,
                status="processing",
                diff_summary="Regenerated asset group using operator instructions",
                revision_payload={"asset_group_id": str(asset_group_id), "feedback": instruction},
            )
        )
        return await self.generate(
            tenant_id=tenant_id,
            plan_id=original_job.content_plan_id,
            feedback=instruction,
            revision_of_job_id=original_job.id,
        )

    async def list_jobs(self, tenant_id: UUID) -> list[ContentJob]:
        return await self.repo.list_jobs(tenant_id)

    async def get_job_detail(self, tenant_id: UUID, job_id: UUID) -> ContentJobResponse:
        job = await self.repo.get_job(tenant_id, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Content job not found")
        assets = await self.repo.list_assets(job.id)
        return ContentJobResponse(
            **{
                "id": job.id,
                "content_plan_id": job.content_plan_id,
                "revision_of_job_id": job.revision_of_job_id,
                "job_type": str(job.job_type),
                "status": str(job.status),
                "stage": str(job.stage),
                "progress": job.progress,
                "feedback": job.feedback,
                "error_message": job.error_message,
                "risk_label": job.grounding_bundle.get("risk_label"),
                "risk_review": job.grounding_bundle.get("risk_review", {}),
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "assets": [
                    GeneratedAssetResponse(
                        id=asset.id,
                        asset_type=str(asset.asset_type),
                        platform=asset.platform,
                        variant_label=asset.variant_label,
                        public_url=asset.public_url,
                        mime_type=asset.mime_type,
                        metadata=asset.asset_metadata,
                        source_trace=asset.source_trace,
                        text_content=asset.text_content,
                    )
                    for asset in assets
                ],
            }
        )
