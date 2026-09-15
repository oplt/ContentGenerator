"""Product Hunter prompt construction and fallback system prompt."""

from __future__ import annotations

from backend.modules.trending_repos.models import TrendingRepo

FALLBACK_PRODUCT_HUNTER_PROMPT = """\
You are an expert Product Hunter with 15+ years of experience identifying breakthrough \
technology products. You have a sharp eye for market gaps, underserved audiences, and \
developer tools that can become billion-dollar businesses. You combine technical depth \
with product intuition — you understand both what engineers build and what users pay for.

When analyzing a GitHub repository, you think about:
- The core technical innovation and what makes it unique
- Real pain points it solves (or could solve with a product wrapper)
- Which audience segments would pay money for this
- How to monetize it (SaaS, API, marketplace, enterprise license, etc.)
- The "wow factor" — what makes someone say "I need this NOW"

You generate bold, concrete, and specific product ideas — not vague suggestions. \
Each idea is something a small team could ship in 3-6 months and get paying customers within a year.
"""


def build_ideas_prompt(record: TrendingRepo, *, readme_excerpt: str | None = None) -> str:
    topics = ", ".join(record.topics[:8]) if record.topics else "N/A"
    readme_section = (
        f"\nREADME excerpt:\n{readme_excerpt}\n" if readme_excerpt else "\nREADME excerpt: N/A\n"
    )
    return (
        f"GitHub repository: **{record.full_name}**\n"
        f"Description: {record.description or 'N/A'}\n"
        f"Language: {record.language or 'N/A'}\n"
        f"Topics: {topics}\n"
        f"Stars: {record.stars_count:,} (gained {record.stars_gained:,} in this period)\n"
        f"URL: {record.html_url}\n"
        f"{readme_section}\n"
        "CRITICAL INSTRUCTION: You MUST return ONLY a valid JSON object. "
        "Do not include any explanatory text, markdown formatting, or code blocks. "
        "Do not wrap the JSON in ```json or ``` tags. Just raw JSON.\n\n"
        "Using the repository metadata and README content above, generate exactly 5 of the most valuable "
        "product ideas that could realistically be built from this repo's capabilities. "
        "Prioritize ideas with clear customer demand, revenue potential, and a strong wedge to market. "
        "Return valid JSON matching the Product Hunter output schema, including repo_assessment "
        "and the full ranked ideas objects.\n\n"
        "EXPECTED JSON STRUCTURE:\n"
        "{\n"
        '  "repo_assessment": {\n'
        '    "what_it_does": "string",\n'
        '    "evidence": ["string"],\n'
        '    "strongest_assets": ["string"],\n'
        '    "main_limitations": ["string"],\n'
        '    "best_commercial_angle": "string",\n'
        '    "confidence": "high|medium|low"\n'
        "  },\n"
        '  "ideas": [\n'
        "    {\n"
        '      "rank": 1,\n'
        '      "title": "string",\n'
        '      "positioning": "string",\n'
        '      "target_customer": "string",\n'
        '      "pain_point": "string",\n'
        '      "product_concept": "string",\n'
        '      "why_this_repo_fits": "string",\n'
        '      "required_extensions": ["string"],\n'
        '      "monetization": {\n'
        '        "model": "string",\n'
        '        "pricing_logic": "string",\n'
        '        "estimated_willingness_to_pay": "string"\n'
        "      },\n"
        '      "scores": {\n'
        '        "revenue_potential": 0,\n'
        '        "customer_urgency": 0,\n'
        '        "repo_leverage": 0,\n'
        '        "speed_to_mvp": 0,\n'
        '        "competitive_intensity": 0\n'
        "      },\n"
        '      "time_to_mvp": "string",\n'
        '      "key_risks": ["string"],\n'
        '      "why_now": "string",\n'
        '      "investor_angle": "string",\n'
        '      "v1_scope": ["string"],\n'
        '      "not_for_v1": ["string"]\n'
        "    }\n"
        "  ]\n"
        "}"
    )


# Historical private-name aliases.
_FALLBACK_PRODUCT_HUNTER_PROMPT = FALLBACK_PRODUCT_HUNTER_PROMPT
_build_ideas_prompt = build_ideas_prompt
