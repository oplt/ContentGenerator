from __future__ import annotations

from backend.modules.content_generation.service import ContentGenerationService
from backend.modules.content_strategy.models import ContentPlan
from backend.modules.story_intelligence.models import StoryCluster


async def test_content_generation_creates_text_assets(db_session, seeded_context):
    tenant = seeded_context["tenant"]
    cluster = StoryCluster(
        tenant_id=tenant.id,
        slug="ai-editor",
        headline="AI editor launches for social media teams",
        summary="A new platform promises faster editorial workflows.",
        primary_topic="ai",
        article_count=3,
        worthy_for_content=True,
        explainability={"keywords": "ai, editor, workflow", "score": "0.83"},
    )
    db_session.add(cluster)
    await db_session.flush()
    plan = ContentPlan(
        tenant_id=tenant.id,
        story_cluster_id=cluster.id,
        status="ready",
        decision="generate",
        content_format="text",
        target_platforms=["x", "bluesky"],
        tone="authoritative",
        urgency="normal",
        recommended_cta="Follow for more.",
        hashtags_strategy="balanced",
        approval_required=True,
        safe_to_publish=True,
        policy_trace={"score": "0.83"},
    )
    db_session.add(plan)
    await db_session.commit()

    service = ContentGenerationService(db_session)
    job = await service.generate(tenant_id=tenant.id, plan_id=plan.id)
    detail = await service.get_job_detail(tenant_id=tenant.id, job_id=job.id)

    assert detail.status == "completed"
    assert any(asset.asset_type == "text_variant" for asset in detail.assets)
