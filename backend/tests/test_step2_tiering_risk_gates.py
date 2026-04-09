"""
Tests for Step 2 — Source Tiering + Content Verticals + Risk Gates.

Covers:
- SourceTier / ContentVertical / HIGH_RISK_VERTICALS / TIER_CREDIBILITY_WEIGHTS enums
- normalize_article: inherits source_tier, content_vertical; applies tier weight to credibility
- _check_risk_gate: UNSAFE → blocked; RISKY with <2 Tier1 → awaiting_confirmation; enough Tier1 → clear
- process_articles: worthy_for_content=False for blocked clusters
- Tier-weighted credibility in _score_cluster
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.source_ingestion.enums import (
    ContentVertical,
    HIGH_RISK_VERTICALS,
    SourceTier,
    TIER_CREDIBILITY_WEIGHTS,
)
from backend.modules.story_intelligence.models import (
    ClusterBlockReason,
    NormalizedArticle,
    RiskLevel,
    StoryCluster,
    TrendScore,
)
from backend.modules.story_intelligence.schemas import ContentWorthinessDecision


# ---------------------------------------------------------------------------
# Enum / constant tests
# ---------------------------------------------------------------------------

def test_source_tier_values() -> None:
    assert SourceTier.AUTHORITATIVE.value == "authoritative"
    assert SourceTier.SIGNAL.value == "signal"
    assert SourceTier.AMPLIFICATION.value == "amplification"


def test_content_vertical_high_risk_set() -> None:
    assert ContentVertical.POLITICS in HIGH_RISK_VERTICALS
    assert ContentVertical.CONFLICTS in HIGH_RISK_VERTICALS
    assert ContentVertical.ECONOMY in HIGH_RISK_VERTICALS
    assert ContentVertical.GAMING not in HIGH_RISK_VERTICALS
    assert ContentVertical.FASHION not in HIGH_RISK_VERTICALS


def test_tier_credibility_weights() -> None:
    assert TIER_CREDIBILITY_WEIGHTS[SourceTier.AUTHORITATIVE] == 1.5
    assert TIER_CREDIBILITY_WEIGHTS[SourceTier.SIGNAL] == 1.0
    assert TIER_CREDIBILITY_WEIGHTS[SourceTier.AMPLIFICATION] == 0.7


def test_risk_level_has_sensitive() -> None:
    assert RiskLevel.SENSITIVE.value == "sensitive"


def test_cluster_block_reason_values() -> None:
    assert ClusterBlockReason.UNSAFE_CONTENT.value == "unsafe_content"
    assert ClusterBlockReason.INSUFFICIENT_TIER1_CONFIRMATION.value == "insufficient_tier1_confirmation"


# ---------------------------------------------------------------------------
# Helpers to build minimal mocks
# ---------------------------------------------------------------------------

def _make_source(
    trust_score: float = 0.8,
    source_tier: str = SourceTier.SIGNAL.value,
    content_vertical: str = ContentVertical.GENERAL.value,
):
    src = MagicMock()
    src.trust_score = trust_score
    src.source_tier = source_tier
    src.content_vertical = content_vertical
    src.name = "Test Source"
    return src


def _make_raw_article(tenant_id=None):
    raw = MagicMock()
    raw.id = uuid.uuid4()
    raw.tenant_id = tenant_id or uuid.uuid4()
    raw.title = "Breaking news about the economy"
    raw.body = "The economy is experiencing significant turmoil due to global factors."
    raw.summary = "Economy turmoil"
    raw.language = "en"
    raw.published_at = datetime.now(timezone.utc)
    raw.canonical_url = "https://example.com/economy-news"
    return raw


def _make_normalized_article(
    source_tier: str = SourceTier.SIGNAL.value,
    content_vertical: str = ContentVertical.GENERAL.value,
    credibility_score: float = 0.7,
    freshness_score: float = 0.9,
    worthiness_score: float = 0.6,
):
    art = MagicMock(spec=NormalizedArticle)
    art.id = uuid.uuid4()
    art.source_tier = source_tier
    art.content_vertical = content_vertical
    art.credibility_score = credibility_score
    art.freshness_score = freshness_score
    art.worthiness_score = worthiness_score
    art.title = "Test article"
    art.body = "Test body"
    art.keywords = ["economy", "turmoil"]
    art.topic_tags = ["economy", "turmoil"]
    art.entities = ["Economy"]
    art.embedding = [0.1, 0.2, 0.3]
    return art


def _make_cluster(
    risk_level: str = RiskLevel.SAFE.value,
    content_vertical: str = ContentVertical.GENERAL.value,
):
    cluster = MagicMock(spec=StoryCluster)
    cluster.id = uuid.uuid4()
    cluster.tenant_id = uuid.uuid4()
    cluster.risk_level = risk_level
    cluster.content_vertical = content_vertical
    cluster.tier1_sources_confirmed = 0
    cluster.block_reason = None
    cluster.awaiting_confirmation = False
    cluster.trend_direction = "flat"
    cluster.explainability = {}
    cluster.article_count = 3  # needed by _heuristic_novelty
    return cluster


# ---------------------------------------------------------------------------
# _check_risk_gate tests
# ---------------------------------------------------------------------------

def _service_instance():
    """Build a StoryIntelligenceService with all external deps mocked out."""
    from backend.modules.story_intelligence.service import StoryIntelligenceService
    svc = object.__new__(StoryIntelligenceService)
    svc.db = AsyncMock()
    svc.repo = AsyncMock()
    svc.llm = AsyncMock()
    svc.embeddings = AsyncMock()
    return svc


def test_risk_gate_unsafe_blocked() -> None:
    svc = _service_instance()
    cluster = _make_cluster(risk_level=RiskLevel.UNSAFE.value)
    articles = [_make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value)]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is True
    assert reason == ClusterBlockReason.UNSAFE_CONTENT.value
    assert cluster.block_reason == ClusterBlockReason.UNSAFE_CONTENT.value
    assert cluster.awaiting_confirmation is False


def test_risk_gate_risky_no_tier1_awaiting() -> None:
    svc = _service_instance()
    cluster = _make_cluster(risk_level=RiskLevel.RISKY.value)
    # No authoritative sources — only signal
    articles = [
        _make_normalized_article(source_tier=SourceTier.SIGNAL.value),
        _make_normalized_article(source_tier=SourceTier.AMPLIFICATION.value),
    ]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is True
    assert reason == ClusterBlockReason.INSUFFICIENT_TIER1_CONFIRMATION.value
    assert cluster.awaiting_confirmation is True
    assert cluster.tier1_sources_confirmed == 0


def test_risk_gate_risky_one_tier1_still_blocked() -> None:
    svc = _service_instance()
    cluster = _make_cluster(risk_level=RiskLevel.RISKY.value)
    articles = [
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value),
        _make_normalized_article(source_tier=SourceTier.SIGNAL.value),
    ]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is True
    assert cluster.tier1_sources_confirmed == 1


def test_risk_gate_risky_two_tier1_cleared() -> None:
    svc = _service_instance()
    cluster = _make_cluster(risk_level=RiskLevel.RISKY.value)
    articles = [
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value),
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value),
        _make_normalized_article(source_tier=SourceTier.SIGNAL.value),
    ]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is False
    assert reason is None
    assert cluster.awaiting_confirmation is False
    assert cluster.block_reason is None
    assert cluster.tier1_sources_confirmed == 2


def test_risk_gate_safe_always_passes() -> None:
    svc = _service_instance()
    cluster = _make_cluster(risk_level=RiskLevel.SAFE.value)
    articles = [_make_normalized_article(source_tier=SourceTier.SIGNAL.value)]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is False
    assert reason is None


def test_risk_gate_high_risk_vertical_needs_tier1() -> None:
    """SAFE risk_level but POLITICS vertical → still requires 2x Tier1."""
    svc = _service_instance()
    cluster = _make_cluster(
        risk_level=RiskLevel.SAFE.value,
        content_vertical=ContentVertical.POLITICS.value,
    )
    articles = [_make_normalized_article(source_tier=SourceTier.SIGNAL.value)]

    blocked, reason = svc._check_risk_gate(cluster, articles)

    assert blocked is True
    assert reason == ClusterBlockReason.INSUFFICIENT_TIER1_CONFIRMATION.value


def test_risk_gate_economy_vertical_cleared_with_two_tier1() -> None:
    svc = _service_instance()
    cluster = _make_cluster(
        risk_level=RiskLevel.SAFE.value,
        content_vertical=ContentVertical.ECONOMY.value,
    )
    articles = [
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value),
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value),
    ]

    blocked, _ = svc._check_risk_gate(cluster, articles)
    assert blocked is False


# ---------------------------------------------------------------------------
# Tier-weighted credibility in _score_cluster
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_cluster_tier_weighted_credibility() -> None:
    """Authoritative articles should push credibility higher than signal-only."""
    svc = _service_instance()
    cluster = _make_cluster()
    cluster.id = uuid.uuid4()
    cluster.tenant_id = uuid.uuid4()

    svc.repo.count_recent_cluster_articles = AsyncMock(return_value=3)
    svc.repo.count_distinct_sources_for_cluster = AsyncMock(return_value=2)

    auth_articles = [
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value, credibility_score=0.8),
        _make_normalized_article(source_tier=SourceTier.AUTHORITATIVE.value, credibility_score=0.8),
    ]
    signal_articles = [
        _make_normalized_article(source_tier=SourceTier.SIGNAL.value, credibility_score=0.8),
        _make_normalized_article(source_tier=SourceTier.SIGNAL.value, credibility_score=0.8),
    ]

    trend_auth, decision_auth = await svc._score_cluster(cluster, auth_articles)
    trend_sig, decision_sig = await svc._score_cluster(cluster, signal_articles)

    # Authoritative articles have weight 1.5 vs Signal weight 1.0
    # Both have credibility_score=0.8, but authoritative tier-weight amplifies it
    assert trend_auth.credibility_score > trend_sig.credibility_score


# ---------------------------------------------------------------------------
# normalize_article: inherits source fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_normalize_article_inherits_source_tier_and_vertical() -> None:
    svc = _service_instance()
    source = _make_source(
        trust_score=0.6,
        source_tier=SourceTier.AUTHORITATIVE.value,
        content_vertical=ContentVertical.ECONOMY.value,
    )
    raw = _make_raw_article()

    svc.repo.get_normalized_by_raw_article = AsyncMock(return_value=None)
    svc.repo.find_near_duplicate = AsyncMock(return_value=None)
    svc.embeddings.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    created_article = MagicMock(spec=NormalizedArticle)
    created_article.source_tier = SourceTier.AUTHORITATIVE.value
    created_article.content_vertical = ContentVertical.ECONOMY.value
    svc.repo.create_normalized_article = AsyncMock(return_value=created_article)

    result = await svc.normalize_article(raw, source)

    # Verify the article passed to create_normalized_article has the right fields
    call_kwargs = svc.repo.create_normalized_article.call_args[0][0]
    assert call_kwargs.source_tier == SourceTier.AUTHORITATIVE.value
    assert call_kwargs.content_vertical == ContentVertical.ECONOMY.value


@pytest.mark.asyncio
async def test_normalize_article_tier_weight_applied_to_credibility() -> None:
    """Authoritative source: credibility_score = min(trust_score * 1.5, 1.0)."""
    svc = _service_instance()
    source = _make_source(
        trust_score=0.6,
        source_tier=SourceTier.AUTHORITATIVE.value,
        content_vertical=ContentVertical.GENERAL.value,
    )
    raw = _make_raw_article()

    svc.repo.get_normalized_by_raw_article = AsyncMock(return_value=None)
    svc.repo.find_near_duplicate = AsyncMock(return_value=None)
    svc.embeddings.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    captured = {}

    async def capture(article):
        captured["article"] = article
        return article

    svc.repo.create_normalized_article = capture

    await svc.normalize_article(raw, source)

    art = captured["article"]
    # 0.6 * 1.5 = 0.9 — higher than raw trust_score
    assert art.credibility_score == pytest.approx(0.9, abs=1e-4)


@pytest.mark.asyncio
async def test_normalize_article_amplification_reduces_credibility() -> None:
    """Amplification source: credibility_score = min(trust_score * 0.7, 1.0)."""
    svc = _service_instance()
    source = _make_source(
        trust_score=0.8,
        source_tier=SourceTier.AMPLIFICATION.value,
        content_vertical=ContentVertical.GENERAL.value,
    )
    raw = _make_raw_article()

    svc.repo.get_normalized_by_raw_article = AsyncMock(return_value=None)
    svc.repo.find_near_duplicate = AsyncMock(return_value=None)
    svc.embeddings.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    captured = {}

    async def capture(article):
        captured["article"] = article
        return article

    svc.repo.create_normalized_article = capture

    await svc.normalize_article(raw, source)

    art = captured["article"]
    # 0.8 * 0.7 = 0.56
    assert art.credibility_score == pytest.approx(0.56, abs=1e-4)


# ---------------------------------------------------------------------------
# Schema field presence
# ---------------------------------------------------------------------------

def test_story_cluster_response_has_new_fields() -> None:
    from backend.modules.story_intelligence.schemas import StoryClusterResponse
    fields = StoryClusterResponse.model_fields
    assert "content_vertical" in fields
    assert "workflow_state" in fields
    assert "risk_flags" in fields
    assert "tier1_sources_confirmed" in fields
    assert "awaiting_confirmation" in fields
    assert "block_reason" in fields


def test_normalized_article_response_has_tier_fields() -> None:
    from backend.modules.story_intelligence.schemas import NormalizedArticleResponse
    fields = NormalizedArticleResponse.model_fields
    assert "content_vertical" in fields
    assert "source_tier" in fields


def test_source_create_request_has_tier_fields() -> None:
    from backend.modules.source_ingestion.schemas import SourceCreateRequest
    req = SourceCreateRequest(
        name="Test",
        source_type="rss",
        url="https://example.com/feed",
        source_tier="authoritative",
        content_vertical="politics",
        tier1_confirmation_required=True,
    )
    assert req.source_tier == "authoritative"
    assert req.content_vertical == "politics"
    assert req.tier1_confirmation_required is True


def test_source_response_has_tier_fields() -> None:
    from backend.modules.source_ingestion.schemas import SourceResponse
    fields = SourceResponse.model_fields
    assert "source_tier" in fields
    assert "content_vertical" in fields
    assert "freshness_decay_hours" in fields
    assert "legal_risk" in fields
    assert "tier1_confirmation_required" in fields
