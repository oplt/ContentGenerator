from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from langdetect import detect
from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.source_ingestion.models import RawArticle, Source
from backend.modules.story_intelligence.models import (
    NormalizedArticle,
    RiskLevel,
    StoryCluster,
    StoryClusterArticle,
    TrendScore,
)
from backend.modules.story_intelligence.providers import (
    cosine_similarity,
    get_embeddings_provider,
    get_llm_provider,
)
from backend.modules.story_intelligence.repository import StoryIntelligenceRepository
from backend.modules.story_intelligence.schemas import (
    ContentWorthinessDecision,
    StoryClusterDetailResponse,
    StoryClusterResponse,
    TrendDashboardResponse,
    TrendScoreResponse,
)


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "from",
    "this",
    "have",
    "will",
    "into",
    "after",
    "about",
    "latest",
}


class StoryIntelligenceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryIntelligenceRepository(db)
        self.llm = get_llm_provider()
        self.embeddings = get_embeddings_provider()

    def _extract_keywords(self, text: str, limit: int = 8) -> list[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
        counts = Counter(token for token in tokens if token not in STOPWORDS)
        return [word for word, _ in counts.most_common(limit)]

    def _infer_language(self, text: str) -> str:
        try:
            return detect(text)
        except Exception:
            return "en"

    def _freshness_score(self, published_at: datetime | None) -> float:
        if not published_at:
            return 0.35
        age_hours = max((datetime.now(timezone.utc) - published_at).total_seconds() / 3600, 0)
        if age_hours <= 6:
            return 1.0
        if age_hours <= 24:
            return 0.8
        if age_hours <= 72:
            return 0.55
        return 0.25

    def _risk_level(self, keywords: list[str]) -> RiskLevel:
        risky_terms = {"war", "attack", "death", "lawsuit", "crisis", "ban"}
        unsafe_terms = {"graphic", "extremist"}
        if any(term in unsafe_terms for term in keywords):
            return RiskLevel.UNSAFE
        if any(term in risky_terms for term in keywords):
            return RiskLevel.RISKY
        return RiskLevel.SAFE

    async def normalize_article(self, raw_article: RawArticle, source: Source) -> NormalizedArticle:
        existing = await self.repo.get_normalized_by_raw_article(raw_article.id)
        if existing:
            return existing
        body = raw_article.body or raw_article.summary or raw_article.title
        keywords = self._extract_keywords(f"{raw_article.title} {body}")
        topic_tags = keywords[:4]
        entities = [token.title() for token in topic_tags[:3]]
        language = raw_article.language or self._infer_language(body)
        embedding = await self.embeddings.embed(f"{raw_article.title}\n{body}")
        freshness_score = self._freshness_score(raw_article.published_at)
        credibility_score = float(source.trust_score)
        worthiness_score = round((freshness_score * 0.4) + (credibility_score * 0.4) + min(len(keywords), 8) / 20, 4)
        article = NormalizedArticle(
            tenant_id=raw_article.tenant_id,
            raw_article_id=raw_article.id,
            title=raw_article.title,
            summary=raw_article.summary,
            body=body,
            canonical_url=raw_article.canonical_url,
            source_name=source.name,
            language=language,
            published_at=raw_article.published_at,
            keywords=keywords,
            topic_tags=topic_tags,
            entities=entities,
            embedding=[f"{value:.4f}" for value in embedding],
            freshness_score=freshness_score,
            credibility_score=credibility_score,
            worthiness_score=worthiness_score,
            explainability={
                "keywords": ", ".join(keywords[:5]),
                "freshness_score": f"{freshness_score:.2f}",
                "credibility_score": f"{credibility_score:.2f}",
            },
        )
        return await self.repo.create_normalized_article(article)

    async def _find_cluster_match(
        self,
        *,
        tenant_id: UUID,
        normalized_article: NormalizedArticle,
    ) -> StoryCluster | None:
        recent_clusters = await self.repo.list_recent_clusters(tenant_id)
        article_embedding = [float(value) for value in normalized_article.embedding]
        for cluster in recent_clusters:
            cluster_keywords = set(cluster.explainability.get("keywords", "").split(", "))
            overlap = len(cluster_keywords.intersection(normalized_article.topic_tags))
            cluster_embedding_text = cluster.explainability.get("embedding", "")
            cluster_embedding = (
                [float(value) for value in cluster_embedding_text.split(",")]
                if cluster_embedding_text
                else []
            )
            similarity = cosine_similarity(article_embedding, cluster_embedding) if cluster_embedding else 0.0
            if overlap >= 2 or similarity >= 0.86:
                return cluster
        return None

    async def _score_cluster(
        self, cluster: StoryCluster, normalized_articles: list[NormalizedArticle]
    ) -> tuple[TrendScore, ContentWorthinessDecision]:
        article_count = len(normalized_articles)
        freshness = max((article.freshness_score for article in normalized_articles), default=0.0)
        credibility = sum(article.credibility_score for article in normalized_articles) / max(article_count, 1)
        momentum = min(article_count / 5, 1.0)
        worthiness = sum(article.worthiness_score for article in normalized_articles) / max(article_count, 1)
        score = round((freshness * 0.35) + (credibility * 0.25) + (momentum * 0.2) + (worthiness * 0.2), 4)
        decision = "generate" if score >= 0.40 else "hold"
        reasons = [
            f"freshness={freshness:.2f}",
            f"credibility={credibility:.2f}",
            f"momentum={momentum:.2f}",
            f"worthiness={worthiness:.2f}",
        ]
        trend = TrendScore(
            tenant_id=cluster.tenant_id,
            story_cluster_id=cluster.id,
            score=score,
            freshness_score=freshness,
            credibility_score=credibility,
            momentum_score=momentum,
            worthiness_score=worthiness,
            calculated_at=datetime.now(timezone.utc),
            explanation={"reasons": "; ".join(reasons)},
        )
        content_decision = ContentWorthinessDecision(
            cluster_id=cluster.id,
            decision=decision,
            score=score,
            reasons=reasons,
        )
        return trend, content_decision

    async def process_articles(self, *, source: Source, raw_articles: list[RawArticle]) -> list[StoryCluster]:
        clusters: list[StoryCluster] = []
        for raw_article in raw_articles:
            normalized = await self.normalize_article(raw_article, source)
            cluster = await self._find_cluster_match(
                tenant_id=raw_article.tenant_id,
                normalized_article=normalized,
            )
            if not cluster:
                summary = await self.llm.summarize(f"{normalized.title}\n{normalized.body}", max_words=60)
                cluster = StoryCluster(
                    tenant_id=raw_article.tenant_id,
                    slug=slugify(normalized.title)[:255],
                    headline=normalized.title,
                    summary=summary,
                    primary_topic=normalized.topic_tags[0] if normalized.topic_tags else "general",
                    representative_article_id=normalized.id,
                    article_count=0,
                    trend_direction="up",
                    worthy_for_content=False,
                    risk_level=self._risk_level(normalized.keywords).value,
                    explainability={
                        "keywords": ", ".join(normalized.topic_tags),
                        "embedding": ",".join(normalized.embedding),
                    },
                )
                cluster = await self.repo.create_cluster(cluster)
            cluster.article_count += 1
            await self.repo.add_cluster_article(
                StoryClusterArticle(
                    story_cluster_id=cluster.id,
                    normalized_article_id=normalized.id,
                    rank=cluster.article_count,
                    is_primary=cluster.article_count == 1,
                )
            )
            normalized_articles = await self.repo.list_normalized_for_cluster(cluster.id)
            trend_score, decision = await self._score_cluster(cluster, normalized_articles)
            cluster.worthy_for_content = decision.decision == "generate"
            cluster.explainability["score"] = f"{decision.score:.2f}"
            await self.repo.create_trend_score(trend_score)
            clusters.append(cluster)
        await self.db.flush()
        return clusters

    async def list_clusters(self, tenant_id: UUID, worthy_only: bool = False) -> list[StoryClusterResponse]:
        clusters = await self.repo.list_clusters(tenant_id=tenant_id, worthy_only=worthy_only)
        responses: list[StoryClusterResponse] = []
        for cluster in clusters:
            trend = await self.repo.get_latest_trend_score(cluster.id)
            responses.append(
                StoryClusterResponse(
                    **cluster.__dict__,
                    latest_trend_score=trend.score if trend else None,
                )
            )
        return responses

    async def get_cluster_detail(self, tenant_id: UUID, cluster_id: UUID) -> StoryClusterDetailResponse | None:
        cluster = await self.repo.get_cluster(tenant_id, cluster_id)
        if not cluster:
            return None
        articles = await self.repo.list_normalized_for_cluster(cluster.id)
        trend = await self.repo.get_latest_trend_score(cluster.id)
        return StoryClusterDetailResponse(
            **cluster.__dict__,
            articles=articles,
            trend_score=TrendScoreResponse.model_validate(trend) if trend else None,
            latest_trend_score=trend.score if trend else None,
        )

    async def trend_dashboard(self, tenant_id: UUID) -> TrendDashboardResponse:
        clusters = await self.list_clusters(tenant_id=tenant_id, worthy_only=False)
        worthy = [cluster for cluster in clusters if cluster.worthy_for_content]
        avg_score = (
            sum(cluster.latest_trend_score or 0.0 for cluster in clusters) / len(clusters)
            if clusters
            else 0.0
        )
        return TrendDashboardResponse(
            summary=[
                {"key": "clusters", "label": "Active clusters", "value": len(clusters)},
                {"key": "worthy", "label": "Content-worthy", "value": len(worthy)},
                {"key": "avg_score", "label": "Average score", "value": round(avg_score, 2)},
            ],
            clusters=clusters[:12],
        )
