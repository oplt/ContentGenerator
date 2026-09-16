"""Fact review node — wraps FactRiskReviewService (rule-based, no LLM)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.modules.fact_review import FactRiskReviewService
from backend.modules.workflows.nodes.base import (
    NodePort,
    NodeResult,
    NodeResultStatus,
    WorkflowNode,
    WorkflowNodeContext,
)


class FactReviewConfig(BaseModel):
    mode: str = Field(default="topic", pattern="^(topic|package)$")
    content_vertical: str = "general"
    topic_risk_level: str = "medium"


class FactReviewInput(BaseModel):
    headline: str = Field(min_length=1)
    summary: str = ""
    claims: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    topic: str | None = None
    generated_texts: dict[str, str] = Field(default_factory=dict)
    evidence_links: list[str] = Field(default_factory=list)
    source_articles: list[Any] = Field(default_factory=list)
    reviewer_issues: list[str] = Field(default_factory=list)


class FactReviewOutput(BaseModel):
    risk_label: str
    blocked: bool
    fail_closed: bool = False
    topic_categories: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    policy_flags: list[Any] = Field(default_factory=list)
    review: dict[str, Any] = Field(default_factory=dict)


class FactReviewNode(WorkflowNode[FactReviewConfig, FactReviewInput, FactReviewOutput]):
    type = "fact_review"
    version = 1
    category = "ai_content"
    display_name = "Fact Review"
    description = "Run fact/risk review via FactRiskReviewService."
    ConfigSchema = FactReviewConfig
    InputSchema = FactReviewInput
    OutputSchema = FactReviewOutput
    required_capabilities: list[str] = []
    input_ports = [
        NodePort(name="headline", data_type="string"),
        NodePort(name="summary", data_type="string", required=False),
        NodePort(name="claims", data_type="array", required=False),
        NodePort(name="keywords", data_type="array", required=False),
        NodePort(name="generated_texts", data_type="object", required=False),
    ]
    output_ports = [
        NodePort(name="risk_label", data_type="string"),
        NodePort(name="blocked", data_type="boolean"),
        NodePort(name="topic_categories", data_type="array"),
        NodePort(name="review", data_type="object"),
    ]

    async def execute(
        self,
        context: WorkflowNodeContext,
        inputs: BaseModel,
        config: BaseModel,
    ) -> NodeResult:
        _ = context
        typed_in = FactReviewInput.model_validate(inputs.model_dump())
        typed_cfg = FactReviewConfig.model_validate(config.model_dump())
        svc = FactRiskReviewService()
        if typed_cfg.mode == "package":
            review = svc.review_generated_package(
                content_vertical=typed_cfg.content_vertical,
                headline=typed_in.headline,
                summary=typed_in.summary,
                topic=typed_in.topic or typed_in.headline,
                topic_risk_level=typed_cfg.topic_risk_level,
                claims=list(typed_in.claims),
                keywords=list(typed_in.keywords),
                source_articles=list(typed_in.source_articles),
                evidence_links=list(typed_in.evidence_links),
                generated_texts=dict(typed_in.generated_texts)
                or {"body": typed_in.summary or typed_in.headline},
                reviewer_issues=list(typed_in.reviewer_issues),
            )
        else:
            review = svc.review_topic(
                content_vertical=typed_cfg.content_vertical,
                headline=typed_in.headline,
                summary=typed_in.summary,
                claims=list(typed_in.claims),
                keywords=list(typed_in.keywords),
            )
        output = FactReviewOutput(
            risk_label=str(review.get("label") or review.get("risk_label") or "unknown"),
            blocked=bool(review.get("blocked")),
            fail_closed=bool(review.get("fail_closed")),
            topic_categories=list(review.get("topic_categories") or []),
            reasons=[str(r) for r in list(review.get("reasons") or [])],
            policy_flags=list(review.get("policy_flags") or []),
            review=dict(review),
        )
        return NodeResult(status=NodeResultStatus.SUCCEEDED, output=output.model_dump())
