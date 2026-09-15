from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.modules.content_generation.quality import hallucination_guard
from backend.modules.story_intelligence.models import NormalizedArticle, StoryCluster
from backend.modules.video_pipeline.schemas import (
    BrandingConfig,
    MediaSequenceItem,
    RenderPreset,
    RendererInput,
    VisualSegment,
)

PLATFORM_LIMITS = {
    "x": 280,
    "bluesky": 300,
    "instagram": 1000,
    "tiktok": 400,
    "youtube_title": 95,
    "youtube_description": 1000,
}


def normalize_text(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", text.lower())).strip()


def sentence_split(text: str) -> list[str]:
    import re

    chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    return chunks or ([text.strip()] if text.strip() else [])


class GenerationContextMixin:
    llm: Any

    def _prompt_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "prompts" / "text_generation" / "v1"

    def _load_template(self, name: str) -> str:
        from backend.core.static_cache import load_prompt_relative

        text = load_prompt_relative(str(self._prompt_dir()), f"{name}.md")
        if text is not None:
            return text
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

    def _normalize_text(self, text: str) -> str:
        return normalize_text(text)

    def _sentence_split(self, text: str) -> list[str]:
        return sentence_split(text)

    def _build_thread(self, headline: str, summary: str, talking_points: list[str], cta: str) -> str:
        thread_parts = [headline.strip()]
        thread_parts.extend(point.strip() for point in talking_points[:3] if point.strip())
        if summary.strip():
            thread_parts.append(summary.strip())
        if cta.strip():
            thread_parts.append(cta.strip())
        return "\n".join(f"{index}. {part}" for index, part in enumerate(thread_parts[:5], start=1))

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
        for match in re.finditer(
            r"(?:^|\n)\s*([ABC])[):.]\s*(.+?)(?=\n\s*[ABC][):.]|\Z)",
            response,
            re.DOTALL,
        ):
            label, text = match.group(1), match.group(2).strip()
            parts[label] = text
        if len(parts) >= 2:
            return [(label, parts[label]) for label in ("A", "B", "C") if label in parts]
        base = f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip()
        return [
            ("A", base),
            ("B", f"{cluster.headline}\n{cluster.summary}\n{cta or 'Follow for more.'} {hashtags}"),
            ("C", f"{cluster.primary_topic.title()} update: {cluster.summary} {hashtags}"),
        ]

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
            title = self._trim(
                await self.llm.generate(title_prompt, max_tokens=50, temperature=0.5),
                PLATFORM_LIMITS["youtube_title"],
            )
            description = self._trim(
                await self.llm.generate(desc_prompt, max_tokens=400, temperature=0.6),
                PLATFORM_LIMITS["youtube_description"],
            )
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
        variants = self._parse_abc_variants(response, cluster, hashtags, cta, limit)
        entities = cluster.explainability.get("keywords", "").split(", ")[:4]
        validated = []
        for label, content in variants:
            if hallucination_guard(content, entities):
                validated.append((label, self._trim(content, limit)))
            else:
                safe = self._trim(
                    f"{cluster.headline}. {cluster.summary} {cta or ''} {hashtags}".strip(),
                    limit,
                )
                validated.append((label, safe))
        return validated

    def _build_renderer_input_payload(
        self,
        *,
        platform: str,
        headline: str,
        summary: str,
        script: str,
        cta: str,
        talking_points: list[str],
        profile: Any = None,
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
            text_color=(
                str(getattr(profile, "visual_style", {}).get("text_color", "#f8fafc"))
                if profile is not None
                else "#f8fafc"
            ),
            accent_color=(
                str(getattr(profile, "visual_style", {}).get("accent_color", "#38bdf8"))
                if profile is not None
                else "#38bdf8"
            ),
            progress_bar=True,
            subtitle_burn_in=True,
            overlay_opacity=(
                float(getattr(profile, "visual_style", {}).get("overlay_opacity", 0.28))
                if profile is not None
                else 0.28
            ),
            font_family=(
                str(getattr(profile, "visual_style", {}).get("font_family", "Sans"))
                if profile is not None
                else "Sans"
            ),
            intro_text=headline,
            outro_text=cta or str(getattr(profile, "default_cta", "") or ""),
        )
        preset = (
            RenderPreset.SQUARE
            if platform == "instagram"
            else RenderPreset.HORIZONTAL
            if platform in {"youtube", "youtube_shorts"}
            else RenderPreset.VERTICAL
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
