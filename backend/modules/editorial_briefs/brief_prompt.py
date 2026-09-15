"""LLM prompt template for editorial brief generation."""

from __future__ import annotations

BRIEF_PROMPT_TEMPLATE = """\
You are an editorial director for a social media content agency.

Story cluster headline: {headline}
Story summary: {summary}
Primary topic: {primary_topic}
Content vertical: {content_vertical}
Risk level: {risk_level}
Keywords: {keywords}
Evidence links: {evidence_links}
Extracted claims: {claims}
{brand_context}
Rewrite instruction: {rewrite_instruction}

Write a concise editorial brief as JSON with these exact keys:
- "topic_title": short title for the trend package
- "why_now": one sentence explaining why the trend matters right now
- "angle": one sentence describing the unique story angle (max 30 words)
- "talking_points": list of 3-5 key points the content must cover
- "recommended_format": one of "text", "video", "both"
- "target_platforms": list of up to 3 platforms from ["x", "instagram", "bluesky", "tiktok", "youtube", "threads"]
- "evidence_links": list of 2-5 trusted evidence links
- "audience_segment": short phrase describing the audience
- "platform_recommendations": list of platform recommendations, may match target_platforms
- "tone_guidance": one-sentence tone instruction (e.g. "authoritative but accessible")
- "cta_strategy": one sentence CTA recommendation
- "caveats": list of caveats or disputed details
- "suggested_formats": list of suggested content formats
- "risk_notes": brief editorial risk warning if any (empty string if none)

Respond with ONLY valid JSON. No markdown fences.
"""
