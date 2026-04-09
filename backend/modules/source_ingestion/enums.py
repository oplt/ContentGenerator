"""
Shared enums for source ingestion and story intelligence.
Placed here to avoid circular imports.
"""
from __future__ import annotations

import enum


class SourceTier(str, enum.Enum):
    """
    Classification of source reliability and authority.

    AUTHORITATIVE (Tier 1):
        Major broadcasters, news wires, official government / institution sources,
        investor relations pages, central banks, IMF/World Bank.
        Required for high-risk content verification.

    SIGNAL (Tier 2):
        Trend discovery sources: Reddit, Google Trends, niche blogs,
        newsletters, YouTube ecosystem signals.
        Used to identify emerging topics but not for single-source truth.

    AMPLIFICATION (Tier 3):
        X/Twitter, Bluesky, forums, comment clusters.
        Secondary popularity and framing signals only.
        Never used as primary evidence for high-risk content.
    """

    AUTHORITATIVE = "authoritative"
    SIGNAL = "signal"
    AMPLIFICATION = "amplification"


class ContentVertical(str, enum.Enum):
    """
    Content topic verticals.
    High-risk verticals (POLITICS, CONFLICTS, ECONOMY) require
    multi-source Tier 1 confirmation before content generation.
    """

    POLITICS = "politics"
    CONFLICTS = "conflicts"
    ECONOMY = "economy"
    GAMING = "gaming"
    FASHION = "fashion"
    BEAUTY = "beauty"
    TECH = "tech"
    ENTERTAINMENT = "entertainment"
    GENERAL = "general"


# Verticals that require stricter risk controls
HIGH_RISK_VERTICALS = {
    ContentVertical.POLITICS,
    ContentVertical.CONFLICTS,
    ContentVertical.ECONOMY,
}

# Tier weight multipliers used in credibility scoring
TIER_CREDIBILITY_WEIGHTS: dict[str, float] = {
    SourceTier.AUTHORITATIVE: 1.5,
    SourceTier.SIGNAL: 1.0,
    SourceTier.AMPLIFICATION: 0.7,
}
